import json
from decimal import Decimal
from typing import Any
from .models import ReconciliationSummary

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj.quantize(Decimal("0.00")))
        return super().default(obj)

def serialize_results(results: list) -> str:
    res_list = []
    for r in results:
        res_list.append({
            "result_id": r.result_id,
            "status": r.status,
            "purchase_record_ids": r.purchase_record_ids,
            "statement_record_ids": r.statement_record_ids,
            "reason": r.reason,
            "field_differences": r.field_differences,
            "validation_issues": r.validation_issues
        })
    return json.dumps(res_list, cls=DecimalEncoder, indent=2)

def serialize_summary(summary: ReconciliationSummary) -> str:
    s_dict = {
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
    return json.dumps(s_dict, indent=2)
