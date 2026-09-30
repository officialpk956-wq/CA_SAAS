import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..db.models import ImportRecord, ValidationIssue as DBValidationIssue, ReconciliationRun, ReconciliationResult, ResultDifference, ImportBatch
from ..models import SourceRow, ValidatedInvoice, ValidationIssue, ReconciliationSummary
from ..reconciliation import reconcile
from ..db.models import utcnow

async def execute_run(db: AsyncSession, run_id: uuid.UUID):
    # Fetch run
    run = await db.get(ReconciliationRun, run_id)
    if not run:
        return
        
    try:
        run.status = "running"
        await db.commit()
        
        # Load purchase records
        p_q = await db.execute(select(ImportRecord).where(ImportRecord.batch_id == run.purchase_batch_id))
        p_records = p_q.scalars().all()
        
        # Load statement records
        s_q = await db.execute(select(ImportRecord).where(ImportRecord.batch_id == run.statement_batch_id))
        s_records = s_q.scalars().all()
        
        # Convert back to engine models
        def to_engine_model(rec: ImportRecord, source_type: str) -> ValidatedInvoice:
            row = SourceRow(source_type, "db", rec.row_number, rec.raw_data)
            return ValidatedInvoice(
                row=row,
                record_id=rec.record_id,
                document_type=rec.document_type,
                supplier_ref=rec.supplier_ref,
                invoice_number=rec.invoice_number,
                invoice_date=rec.invoice_date,
                taxable_value=rec.taxable_value,
                cgst=rec.cgst,
                sgst=rec.sgst,
                igst=rec.igst,
                cess=rec.cess,
                invoice_total=rec.invoice_total
            )

        valid_p = []
        valid_s = []
        val_issues = []
        
        # To get validation reasons efficiently, fetch all for both batches
        db_issues_q = await db.execute(
            select(DBValidationIssue, ImportRecord.row_number, ImportRecord.raw_data, ImportBatch.source_type)
            .join(ImportRecord, DBValidationIssue.record_id == ImportRecord.id)
            .join(ImportBatch, ImportRecord.batch_id == ImportBatch.id)
            .where(ImportBatch.id.in_([run.purchase_batch_id, run.statement_batch_id]))
        )
        
        for db_iss, r_num, raw, s_type in db_issues_q:
            val_issues.append(ValidationIssue(
                row=SourceRow(s_type, "db", r_num, raw),
                reason=db_iss.reason
            ))

        for rec in p_records:
            if rec.is_valid:
                valid_p.append(to_engine_model(rec, "purchase"))
                
        for rec in s_records:
            if rec.is_valid:
                valid_s.append(to_engine_model(rec, "statement"))
                
        # Run Phase 2 engine
        results, summary = reconcile(valid_p, valid_s, val_issues, len(p_records), len(s_records))
        
        # Persist results
        db_results = []
        db_diffs = []
        
        for r in results:
            dr = ReconciliationResult(
                run_id=run.id,
                result_id=r.result_id,
                status=r.status,
                reason=r.reason,
                purchase_record_ids={"ids": r.purchase_record_ids},
                statement_record_ids={"ids": r.statement_record_ids},
                validation_issues={"issues": r.validation_issues, "source_row_number": r.source_row_number}
            )
            db.add(dr)
            await db.flush() # need ID for diffs
            
            for k, v in r.field_differences.items():
                db_diffs.append(ResultDifference(
                    reconciliation_result_id=dr.id,
                    field_name=k,
                    difference_value=v
                ))
                
        db.add_all(db_diffs)
        
        run.summary_data = {
            "purchase_rows_total": summary.purchase_rows_total,
            "statement_rows_total": summary.statement_rows_total,
            "purchase_rows_valid": summary.purchase_rows_valid,
            "purchase_rows_invalid": summary.purchase_rows_invalid,
            "statement_rows_valid": summary.statement_rows_valid,
            "statement_rows_invalid": summary.statement_rows_invalid,
            "distinct_results_by_status": summary.distinct_results_by_status,
            "matched_pair_count": summary.matched_pair_count,
            "duplicate_group_count": summary.duplicate_group_count,
            "unique_source_rows_accounted_for": summary.unique_source_rows_accounted_for
        }
        
        run.status = "succeeded"
        run.completed_at = utcnow()
        await db.commit()
        
    except Exception as e:
        await db.rollback()
        # In a new transaction, mark failed
        run = await db.get(ReconciliationRun, run_id)
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = utcnow()
        await db.commit()
