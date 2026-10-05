import csv
import json
from pathlib import Path
from decimal import Decimal
from backend.gst_copilot.parser import parse_purchases, parse_statements, parse_suppliers
from backend.gst_copilot.validation import validate_datasets
from backend.gst_copilot.reconciliation import reconcile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "sample_data" / "v1"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "reconciliation_v1"

def test_acceptance_against_answer_key():
    # 1. Run engine
    sup = parse_suppliers(DATA_DIR / "suppliers.csv")
    pur = parse_purchases(DATA_DIR / "purchase_register.csv")
    stmt = parse_statements(DATA_DIR / "gstr2b_demo.csv")
    vp, vs, issues = validate_datasets(pur, stmt, sup)
    res, summary = reconcile(vp, vs, issues, len(pur), len(stmt))

    # 2. Load expected
    with open(FIXTURES_DIR / "expected_results.csv", 'r', encoding='utf-8') as f:
        expected_csv = list(csv.DictReader(f))
    with open(FIXTURES_DIR / "expected_summary.json", 'r', encoding='utf-8') as f:
        expected_summary = json.load(f)

    # 3. Compare summary
    assert summary.purchase_rows_total == expected_summary["purchase_rows_total"]
    assert summary.statement_rows_total == expected_summary["statement_rows_total"]
    assert summary.purchase_rows_valid == expected_summary["purchase_rows_valid"]
    assert summary.statement_rows_valid == expected_summary["statement_rows_valid"]
    assert summary.matched_pair_count == expected_summary["matched_pair_count"]
    assert summary.duplicate_group_count == expected_summary["duplicate_group_count"]
    assert summary.unique_source_rows_accounted_for == expected_summary["unique_source_rows_accounted_for"]
    
    for k, v in expected_summary["distinct_results_by_status"].items():
        assert summary.distinct_results_by_status.get(k, 0) == v

    # 4. Compare results
    # Group expected by result_id
    exp_groups = {}
    for row in expected_csv:
        rid = row["result_id"]
        if rid not in exp_groups:
            exp_groups[rid] = {
                "status": row["expected_status"],
                "purchase_record_ids": set(row["purchase_record_ids"].split('|')) - {''},
                "statement_record_ids": set(row["statement_record_ids"].split('|')) - {''},
                "diffs": {}
            }
        if row["difference_field"]:
            exp_groups[rid]["diffs"][row["difference_field"]] = Decimal(row["expected_difference"])

    # Canonicalize and compare (status, p_ids, s_ids)
    def canonical_key(g):
        return (g["status"], tuple(sorted(g["purchase_record_ids"])), tuple(sorted(g["statement_record_ids"])))

    exp_canonical = {canonical_key(g): g for g in exp_groups.values()}
    
    act_canonical = {}
    for r in res:
        key = (r.status, tuple(sorted(r.purchase_record_ids)), tuple(sorted(r.statement_record_ids)))
        act_canonical[key] = r
        
    assert len(exp_canonical) == len(act_canonical)
    
    for key, exp_g in exp_canonical.items():
        assert key in act_canonical, f"Missing expected group: {key}"
        act_g = act_canonical[key]
        assert act_g.field_differences == exp_g["diffs"]
