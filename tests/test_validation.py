import pytest
from backend.gst_copilot.models import SourceRow, ValidatedInvoice, ValidationIssue
from backend.gst_copilot.validation import validate_row

def make_row(data):
    base = {
        "record_id": "R1",
        "supplier_ref": "S1",
        "invoice_number": "INV1",
        "document_type": "invoice",
        "invoice_date": "2026-08-01",
        "taxable_value": "100.00",
        "cgst": "9.00",
        "sgst": "9.00",
        "igst": "0.00",
        "cess": "0.00",
        "invoice_total": "118.00"
    }
    base.update(data)
    return SourceRow(source_type="purchase", filename="test.csv", row_number=2, raw_data=base)

def test_validate_success():
    r = make_row({})
    v = validate_row(r, {"S1"})
    assert isinstance(v, ValidatedInvoice)

def test_missing_record_id():
    r = make_row({"record_id": ""})
    v = validate_row(r, {"S1"})
    assert isinstance(v, ValidationIssue)
    assert "Missing record_id" in v.reason

def test_invalid_supplier():
    r = make_row({})
    v = validate_row(r, {"S2"}) # S1 not in S2
    assert isinstance(v, ValidationIssue)
    assert "not found in supplier list" in v.reason

def test_invalid_date():
    r = make_row({"invoice_date": "2026/08/01"})
    v = validate_row(r, {"S1"})
    assert isinstance(v, ValidationIssue)
    assert "Invalid date format" in v.reason

def test_invalid_amounts():
    r = make_row({"taxable_value": "ABC"})
    v = validate_row(r, {"S1"})
    assert isinstance(v, ValidationIssue)
    assert "Invalid decimal" in v.reason or "Invalid numeric" in v.reason

def test_negative_amounts():
    r = make_row({"taxable_value": "-100.00", "invoice_total": "-118.00"})
    v = validate_row(r, {"S1"})
    assert isinstance(v, ValidationIssue)
    assert "negative" in v.reason.lower()

def test_blank_amounts():
    r = make_row({"taxable_value": ""})
    v = validate_row(r, {"S1"})
    assert isinstance(v, ValidationIssue)
    assert "Blank amounts" in v.reason

def test_total_mismatch():
    r = make_row({"invoice_total": "119.00"})
    v = validate_row(r, {"S1"})
    assert isinstance(v, ValidationIssue)
    assert "sum of components" in v.reason

@pytest.mark.parametrize("date", ["01-08-2026", "2026-8-1"])
def test_reject_undocumented_date_formats(date):
    assert isinstance(validate_row(make_row({"invoice_date": date}), {"S1"}), ValidationIssue)

@pytest.mark.parametrize("amount", ["100.001", "1000000000000.00", "NaN", "Infinity"])
def test_reject_unpersistable_amounts(amount):
    assert isinstance(validate_row(make_row({"taxable_value": amount}), {"S1"}), ValidationIssue)
