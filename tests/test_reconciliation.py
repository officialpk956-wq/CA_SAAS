import pytest
from decimal import Decimal
from backend.gst_copilot.models import SourceRow, ValidatedInvoice, ValidationIssue
from backend.gst_copilot.reconciliation import reconcile

def make_vi(rid, sup, inv, dt, taxb, cgst=0, sgst=0, igst=0, source="purchase"):
    taxb = Decimal(str(taxb))
    cgst = Decimal(str(cgst))
    sgst = Decimal(str(sgst))
    igst = Decimal(str(igst))
    cess = Decimal("0.00")
    total = taxb + cgst + sgst + igst + cess
    
    row = SourceRow(source, "file.csv", 2, {"record_id": rid})
    return ValidatedInvoice(
        row=row,
        record_id=rid,
        document_type="invoice",
        supplier_ref=sup,
        invoice_number=inv,
        invoice_date=dt,
        taxable_value=taxb,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        cess=cess,
        invoice_total=total
    )

def test_exact_match():
    p = make_vi("P1", "S1", "INV1", "2026-08-01", 100)
    s = make_vi("S1", "S1", "INV1", "2026-08-01", 100, source="statement")
    res, sumy = reconcile([p], [s], [], 1, 1)
    
    assert len(res) == 1
    assert res[0].status == "matched"
    assert sumy.matched_pair_count == 1

def test_amount_mismatch():
    p = make_vi("P1", "S1", "INV1", "2026-08-01", 100)
    s = make_vi("S1", "S1", "INV1", "2026-08-01", 120, source="statement")
    res, sumy = reconcile([p], [s], [], 1, 1)
    
    assert len(res) == 1
    assert res[0].status == "amount_mismatch"
    assert "taxable_value" in res[0].field_differences
    assert res[0].field_differences["taxable_value"] == Decimal("-20.00")
    assert sumy.matched_pair_count == 0

def test_date_conflict():
    p = make_vi("P1", "S1", "INV1", "2026-08-01", 100)
    s = make_vi("S1", "S1", "INV1", "2026-08-02", 100, source="statement")
    res, _ = reconcile([p], [s], [], 1, 1)
    
    assert res[0].status == "date_conflict"

def test_books_only_statement_only():
    p = make_vi("P1", "S1", "INV1", "2026-08-01", 100)
    s = make_vi("S1", "S1", "INV2", "2026-08-02", 100, source="statement")
    res, _ = reconcile([p], [s], [], 1, 1)
    
    assert len(res) == 2
    statuses = {r.status for r in res}
    assert statuses == {"books_only", "statement_only"}

def test_duplicate_candidate():
    p1 = make_vi("P1", "S1", "INV1", "2026-08-01", 100)
    p2 = make_vi("P2", "S1", "INV1", "2026-08-01", 100)
    s = make_vi("S1", "S1", "INV1", "2026-08-01", 100, source="statement")
    res, sumy = reconcile([p1, p2], [s], [], 2, 1)
    
    assert len(res) == 1
    assert res[0].status == "duplicate_candidate"
    assert sumy.duplicate_group_count == 1
    assert set(res[0].purchase_record_ids) == {"P1", "P2"}


def test_result_ids_keep_part_boundaries():
    from backend.gst_copilot.reconciliation import generate_result_id
    # Old string concatenation made these two inputs identical.
    assert generate_result_id(["S", "invoice", "INV1"], ["0"], []) != generate_result_id(["S", "invoice", "INV10"], [], [])
    assert len(generate_result_id("x")) == len("RES-") + 16

def test_validation_error_keeps_physical_row_for_blank_ids():
    rows = [SourceRow("purchase", "f.csv", n, {"record_id": ""}) for n in (2, 3)]
    issues = [ValidationIssue(r, "Missing record_id.") for r in rows]
    res, _ = reconcile([], [], issues, 2, 0)
    assert sorted(r.source_row_number for r in res) == [2, 3]
    assert len({r.result_id for r in res}) == 2

def test_export_keeps_negative_amounts_but_neutralises_formulas():
    from backend.gst_copilot.services.export_service import sanitize_value
    assert sanitize_value("-200.00") == "-200.00"
    assert sanitize_value("=1+1") == "'=1+1"
    assert sanitize_value("-1+cmd") == "'-1+cmd"
    assert sanitize_value("@SUM(A1)") == "'@SUM(A1)"
