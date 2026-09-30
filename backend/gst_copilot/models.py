from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

@dataclass(frozen=True)
class SourceRow:
    source_type: str  # 'purchase' or 'statement'
    filename: str
    row_number: int
    raw_data: Dict[str, str]

@dataclass(frozen=True)
class ValidationIssue:
    row: SourceRow
    reason: str

@dataclass(frozen=True)
class ValidatedInvoice:
    row: SourceRow
    record_id: str
    document_type: str
    supplier_ref: str
    invoice_number: str
    invoice_date: str  # YYYY-MM-DD
    taxable_value: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    cess: Decimal
    invoice_total: Decimal

    @property
    def base_identity(self):
        return (self.supplier_ref, self.document_type, self.invoice_number)

@dataclass(frozen=True)
class ReconciliationResult:
    result_id: str
    status: str
    purchase_record_ids: List[str]
    statement_record_ids: List[str]
    reason: str
    field_differences: Dict[str, Decimal] = field(default_factory=dict)
    validation_issues: List[str] = field(default_factory=list)
    # Physical source row for validation errors, whose record_id may be blank.
    source_row_number: Optional[int] = None

@dataclass
class ReconciliationSummary:
    purchase_rows_total: int = 0
    statement_rows_total: int = 0
    purchase_rows_valid: int = 0
    purchase_rows_invalid: int = 0
    statement_rows_valid: int = 0
    statement_rows_invalid: int = 0
    distinct_results_by_status: Dict[str, int] = field(default_factory=dict)
    matched_pair_count: int = 0
    duplicate_group_count: int = 0
    unique_source_rows_accounted_for: int = 0
