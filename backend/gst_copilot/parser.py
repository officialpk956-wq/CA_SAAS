import csv
from typing import List, Set
from pathlib import Path
from .models import SourceRow

class ParserError(Exception):
    """Exception raised for unrecoverable parsing errors (e.g., malformed headers)."""
    pass

PURCHASE_HEADERS = {
    "record_id", "document_type", "supplier_ref", "invoice_number", 
    "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", 
    "invoice_total", "description"
}

STATEMENT_HEADERS = {
    "record_id", "document_type", "supplier_ref", "invoice_number", 
    "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", 
    "invoice_total"
}

SUPPLIER_HEADERS = {
    "supplier_ref", "supplier_name", "business_category"
}

def parse_csv(filepath: str, source_type: str, expected_headers: Set[str]) -> List[SourceRow]:
    path = Path(filepath)
    if not path.exists():
        raise ParserError(f"File not found: {filepath}")

    rows: List[SourceRow] = []
    
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        try:
            header_row = next(reader)
        except StopIteration:
            raise ParserError(f"File is completely empty: {filepath}")

        # Check for duplicate headers
        if len(header_row) != len(set(header_row)):
            raise ParserError(f"Duplicate headers found in: {filepath}")

        # Check required headers
        actual_headers = set(header_row)
        missing_headers = expected_headers - actual_headers
        if missing_headers:
            raise ParserError(f"Missing required headers in {filepath}: {missing_headers}")

        for i, row in enumerate(reader, start=2):
            if not row:
                continue # ignore completely empty rows
            
            # Ensure row length matches header length (or dict zip logic)
            if len(row) > len(header_row):
                raise ParserError(f"Row {i} has more fields than headers in {filepath}")
            
            # Zip creates the dict. Missing trailing values become empty string or we can pad them.
            # DictReader handles this usually, but it sets None for missing or a list for extra.
            # We already handled extra fields. For missing fields, pad with empty strings.
            row_data = {header: (row[j] if j < len(row) else "") for j, header in enumerate(header_row)}
            
            # Just ignore completely empty line represented as a list of empty strings
            if all(v.strip() == "" for v in row_data.values()):
                continue

            rows.append(SourceRow(
                source_type=source_type,
                filename=path.name,
                row_number=i,
                raw_data=row_data
            ))
            
    return rows

def parse_purchases(filepath: str) -> List[SourceRow]:
    return parse_csv(filepath, "purchase", PURCHASE_HEADERS)

def parse_statements(filepath: str) -> List[SourceRow]:
    return parse_csv(filepath, "statement", STATEMENT_HEADERS)

def parse_suppliers(filepath: str) -> Set[str]:
    # Custom parser for suppliers to return set of supplier_refs
    rows = parse_csv(filepath, "supplier", SUPPLIER_HEADERS)
    return {r.raw_data["supplier_ref"] for r in rows if r.raw_data.get("supplier_ref")}
