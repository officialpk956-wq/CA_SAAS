import hashlib
import json
from collections import defaultdict
from typing import List, Dict, Tuple
from decimal import Decimal
from .models import ValidatedInvoice, ValidationIssue, ReconciliationResult, ReconciliationSummary

def generate_result_id(*parts) -> str:
    """Stable ID from structured parts; JSON keeps part boundaries unambiguous."""
    h = hashlib.sha256(json.dumps(parts).encode('utf-8')).hexdigest()[:16]
    return f"RES-{h.upper()}"

def reconcile(
    valid_purchases: List[ValidatedInvoice],
    valid_statements: List[ValidatedInvoice],
    validation_issues: List[ValidationIssue],
    purchase_total_count: int,
    statement_total_count: int
) -> Tuple[List[ReconciliationResult], ReconciliationSummary]:
    
    pur_by_identity = defaultdict(list)
    stmt_by_identity = defaultdict(list)
    
    for p in valid_purchases:
        pur_by_identity[p.base_identity].append(p)
        
    for s in valid_statements:
        stmt_by_identity[s.base_identity].append(s)
        
    all_identities = sorted(list(set(pur_by_identity.keys()) | set(stmt_by_identity.keys())))
    
    results: List[ReconciliationResult] = []
    
    # Process validation issues first
    # Sort issues for determinism
    validation_issues.sort(key=lambda i: (i.row.source_type, i.row.row_number, i.row.raw_data.get('record_id', '')))
    
    for i, issue in enumerate(validation_issues):
        rec_id = issue.row.raw_data.get('record_id', '')
        # Deterministic ID for validation error
        res_id = generate_result_id("val", issue.row.source_type, rec_id, issue.row.row_number)

        p_ids = [rec_id] if issue.row.source_type == 'purchase' else []
        s_ids = [rec_id] if issue.row.source_type == 'statement' else []

        results.append(ReconciliationResult(
            result_id=res_id,
            status="validation_error",
            purchase_record_ids=p_ids,
            statement_record_ids=s_ids,
            reason=issue.reason,
            validation_issues=[issue.reason],
            source_row_number=issue.row.row_number
        ))
    
    for identity in all_identities:
        p_records = sorted(pur_by_identity[identity], key=lambda x: x.record_id)
        s_records = sorted(stmt_by_identity[identity], key=lambda x: x.record_id)
        
        p_ids = [x.record_id for x in p_records]
        s_ids = [x.record_id for x in s_records]
        
        res_id = generate_result_id(list(identity), p_ids, s_ids)
        
        if len(p_records) > 1 or len(s_records) > 1:
            results.append(ReconciliationResult(
                result_id=res_id,
                status="duplicate_candidate",
                purchase_record_ids=p_ids,
                statement_record_ids=s_ids,
                reason="Duplicate records found for this identity."
            ))
            continue
            
        if len(p_records) == 1 and len(s_records) == 0:
            results.append(ReconciliationResult(
                result_id=res_id,
                status="books_only",
                purchase_record_ids=p_ids,
                statement_record_ids=[],
                reason="Valid counterpart is unmatched in statement."
            ))
            continue
            
        if len(p_records) == 0 and len(s_records) == 1:
            results.append(ReconciliationResult(
                result_id=res_id,
                status="statement_only",
                purchase_record_ids=[],
                statement_record_ids=s_ids,
                reason="Valid counterpart is unmatched in purchases."
            ))
            continue
            
        # Exactly 1:1 match candidate
        p = p_records[0]
        s = s_records[0]
        
        if p.invoice_date != s.invoice_date:
            results.append(ReconciliationResult(
                result_id=res_id,
                status="date_conflict",
                purchase_record_ids=p_ids,
                statement_record_ids=s_ids,
                reason="Dates differ."
            ))
            continue
            
        # Check amounts
        diffs = {}
        fields = ["taxable_value", "cgst", "sgst", "igst", "cess", "invoice_total"]
        for f in fields:
            p_val = getattr(p, f)
            s_val = getattr(s, f)
            if p_val != s_val:
                diffs[f] = p_val - s_val
                
        if diffs:
            results.append(ReconciliationResult(
                result_id=res_id,
                status="amount_mismatch",
                purchase_record_ids=p_ids,
                statement_record_ids=s_ids,
                reason="Amount mismatch.",
                field_differences=diffs
            ))
        else:
            results.append(ReconciliationResult(
                result_id=res_id,
                status="matched",
                purchase_record_ids=p_ids,
                statement_record_ids=s_ids,
                reason="Exact match."
            ))

    # Summary
    # Sort results for deterministic output order
    results.sort(key=lambda r: (r.status, "|".join(r.purchase_record_ids), "|".join(r.statement_record_ids)))

    status_counts = defaultdict(int)
    matched_pair_count = 0
    duplicate_group_count = 0
    
    unique_rows_accounted = set()
    
    for r in results:
        status_counts[r.status] += 1
        if r.status == "matched":
            matched_pair_count += 1
        elif r.status == "duplicate_candidate":
            duplicate_group_count += 1
            
        for p in r.purchase_record_ids:
            if p: unique_rows_accounted.add(f"p:{p}")
        for s in r.statement_record_ids:
            if s: unique_rows_accounted.add(f"s:{s}")
            
    # Include rows that might not have a record_id but were parsed.
    # The requirement says "Every parsed source row belongs to exactly one result group".
    # We handled validation errors which include all rejected rows, and the matching engine handled all valid rows.
    # Let's count them accurately.
    total_parsed_rows_accounted = len(valid_purchases) + len(valid_statements) + len(validation_issues)
    if total_parsed_rows_accounted != purchase_total_count + statement_total_count:
        raise RuntimeError("Source rows not fully accounted for.")

    summary = ReconciliationSummary(
        purchase_rows_total=purchase_total_count,
        statement_rows_total=statement_total_count,
        purchase_rows_valid=len(valid_purchases),
        purchase_rows_invalid=purchase_total_count - len(valid_purchases),
        statement_rows_valid=len(valid_statements),
        statement_rows_invalid=statement_total_count - len(valid_statements),
        distinct_results_by_status=dict(status_counts),
        matched_pair_count=matched_pair_count,
        duplicate_group_count=duplicate_group_count,
        unique_source_rows_accounted_for=total_parsed_rows_accounted
    )
    
    return results, summary
