import pytest
import tempfile
import csv
from pathlib import Path
from backend.gst_copilot.parser import parse_purchases, parse_statements, parse_suppliers, ParserError, PURCHASE_HEADERS

def test_parse_purchases_success():
    headers = ["record_id", "document_type", "supplier_ref", "invoice_number", 
               "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", 
               "invoice_total", "description"]
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerow(["PUR-001", "invoice", "DEMO-SUP-001", "INV-001", "2026-08-01", "100", "9", "9", "0", "0", "118", "Test"])
        f_name = f.name
        
    rows = parse_purchases(f_name)
    assert len(rows) == 1
    assert rows[0].raw_data["record_id"] == "PUR-001"
    Path(f_name).unlink()

def test_parse_empty_file():
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
        f_name = f.name
    with pytest.raises(ParserError, match="completely empty"):
        parse_purchases(f_name)
    Path(f_name).unlink()

def test_parse_header_only():
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(list(PURCHASE_HEADERS))
        f_name = f.name
    rows = parse_purchases(f_name)
    assert len(rows) == 0
    Path(f_name).unlink()

def test_parse_duplicate_headers():
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
        writer = csv.writer(f)
        h = list(PURCHASE_HEADERS)
        h[1] = h[0] # duplicate
        writer.writerow(h)
        f_name = f.name
    with pytest.raises(ParserError, match="Duplicate headers"):
        parse_purchases(f_name)
    Path(f_name).unlink()

def test_parse_missing_headers():
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
        writer = csv.writer(f)
        h = list(PURCHASE_HEADERS)[:-1] # missing one
        writer.writerow(h)
        f_name = f.name
    with pytest.raises(ParserError, match="Missing required headers"):
        parse_purchases(f_name)
    Path(f_name).unlink()

def test_parse_bom_handling():
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(list(PURCHASE_HEADERS))
        writer.writerow(["PUR-001"] + [""] * (len(PURCHASE_HEADERS)-1))
        f_name = f.name
    rows = parse_purchases(f_name)
    # The BOM shouldn't mess up the first header name
    assert set(rows[0].raw_data.keys()) == PURCHASE_HEADERS
    Path(f_name).unlink()
