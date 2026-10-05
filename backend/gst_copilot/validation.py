import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Set, Tuple, Union, List
from .models import SourceRow, ValidatedInvoice, ValidationIssue

GSTIN_SHAPE = re.compile(r'\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]')

def parse_decimal(value_str: str) -> Decimal:
    """Parse a strict decimal. No blanks, no currency symbols, no commas."""
    if not value_str or not value_str.strip():
        raise ValueError("Blank amounts are not allowed.")
    
    # Must look like a number (optional sign, digits, optional decimal point and digits)
    # The requirement says "Reject nonnumeric, nonfinite, currency-symbol, and thousands-separated values."
    # Also "negative values are unsupported"
    if not re.match(r'^\d{1,12}\.\d{2}$', value_str.strip()):
        raise ValueError("Invalid numeric format or negative value.")
        
    try:
        val = Decimal(value_str.strip())
        if not val.is_finite():
            raise ValueError("Non-finite amounts are not allowed.")
        return val
    except InvalidOperation:
        raise ValueError("Invalid decimal.")

def validate_row(row: SourceRow, valid_suppliers: Set[str]) -> Union[ValidatedInvoice, ValidationIssue]:
    d = row.raw_data
    
    # Check required identifiers
    record_id = d.get("record_id", "").strip()
    supplier_ref = d.get("supplier_ref", "").strip()
    invoice_number = d.get("invoice_number", "").strip()
    document_type = d.get("document_type", "").strip()
    invoice_date_str = d.get("invoice_date", "").strip()

    if not record_id:
        return ValidationIssue(row, "Missing record_id.")
    if not supplier_ref:
        return ValidationIssue(row, "Missing supplier_ref.")
    if not invoice_number:
        return ValidationIssue(row, "Missing invoice_number.")
    
    # Demo supplier list, or a GSTIN-shaped reference (format check only; no checksum, no portal lookup).
    if supplier_ref not in valid_suppliers and not GSTIN_SHAPE.fullmatch(supplier_ref):
        return ValidationIssue(row, f"Supplier reference '{supplier_ref}' not found in supplier list.")
        
    if document_type != "invoice":
        return ValidationIssue(row, "Document type must be 'invoice'.")

    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", invoice_date_str):
            raise ValueError()
        datetime.strptime(invoice_date_str, "%Y-%m-%d")
    except ValueError:
        return ValidationIssue(row, "Invalid date format, must be YYYY-MM-DD.")

    try:
        taxable_value = parse_decimal(d.get("taxable_value", ""))
        cgst = parse_decimal(d.get("cgst", ""))
        sgst = parse_decimal(d.get("sgst", ""))
        igst = parse_decimal(d.get("igst", ""))
        cess = parse_decimal(d.get("cess", ""))
        invoice_total = parse_decimal(d.get("invoice_total", ""))
    except ValueError as e:
        return ValidationIssue(row, str(e))

    calculated_total = taxable_value + cgst + sgst + igst + cess
    if invoice_total != calculated_total:
        return ValidationIssue(row, "invoice_total does not match the sum of components.")

    return ValidatedInvoice(
        row=row,
        record_id=record_id,
        document_type=document_type,
        supplier_ref=supplier_ref,
        invoice_number=invoice_number, # preserving original string
        invoice_date=invoice_date_str,
        taxable_value=taxable_value,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        cess=cess,
        invoice_total=invoice_total
    )

def validate_datasets(
    purchases: List[SourceRow], 
    statements: List[SourceRow], 
    valid_suppliers: Set[str]
) -> Tuple[List[ValidatedInvoice], List[ValidatedInvoice], List[ValidationIssue]]:
    
    valid_p = []
    valid_s = []
    issues = []
    
    # Check uniqueness of record_ids globally across the file
    def check_uniqueness(rows: List[SourceRow], file_desc: str):
        seen = set()
        for r in rows:
            rid = r.raw_data.get("record_id", "").strip()
            if not rid:
                continue
            if rid in seen:
                raise ValueError(f"Duplicate record ID '{rid}' found in {file_desc}.")
            seen.add(rid)
            
    check_uniqueness(purchases, "purchases")
    check_uniqueness(statements, "statements")

    for p in purchases:
        res = validate_row(p, valid_suppliers)
        if isinstance(res, ValidatedInvoice):
            valid_p.append(res)
        else:
            issues.append(res)
            
    for s in statements:
        res = validate_row(s, valid_suppliers)
        if isinstance(res, ValidatedInvoice):
            valid_s.append(res)
        else:
            issues.append(res)
            
    return valid_p, valid_s, issues
