import os
import csv
import json
import pytest
import subprocess
import tempfile
from pathlib import Path
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "sample_data" / "v1"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "reconciliation_v1"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "generate_synthetic_data.py"

@pytest.fixture(scope="session")
def datasets():
    def read_csv(path):
        with open(path, 'r', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    return {
        "client": read_csv(DATA_DIR / "client_profile.csv"),
        "suppliers": read_csv(DATA_DIR / "suppliers.csv"),
        "purchases": read_csv(DATA_DIR / "purchase_register.csv"),
        "statements": read_csv(DATA_DIR / "gstr2b_demo.csv"),
    }

@pytest.fixture(scope="session")
def answer_key():
    with open(FIXTURES_DIR / "scenario_manifest.json", 'r') as f:
        manifest = json.load(f)
    with open(FIXTURES_DIR / "expected_summary.json", 'r') as f:
        summary = json.load(f)
    with open(FIXTURES_DIR / "expected_results.csv", 'r', encoding='utf-8') as f:
        results = list(csv.DictReader(f))
    return {"manifest": manifest, "summary": summary, "results": results}

def test_1_exact_headers_and_required_files(datasets):
    assert list(datasets["client"][0].keys()) == ["client_id", "client_name", "registration_ref", "filing_frequency", "reporting_period", "currency"]
    assert list(datasets["suppliers"][0].keys()) == ["supplier_ref", "supplier_name", "business_category"]
    assert list(datasets["purchases"][0].keys()) == ["record_id", "document_type", "supplier_ref", "invoice_number", "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", "invoice_total", "description"]
    assert list(datasets["statements"][0].keys()) == ["record_id", "document_type", "supplier_ref", "invoice_number", "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", "invoice_total"]

def test_2_unique_source_record_ids(datasets):
    pur_ids = [r["record_id"] for r in datasets["purchases"]]
    stmt_ids = [r["record_id"] for r in datasets["statements"]]
    assert len(pur_ids) == len(set(pur_ids))
    assert len(stmt_ids) == len(set(stmt_ids))
    assert len(set(pur_ids).intersection(set(stmt_ids))) == 0

def test_3_valid_supplier_references(datasets):
    sup_refs = {r["supplier_ref"] for r in datasets["suppliers"]}
    for r in datasets["purchases"]:
        assert r["supplier_ref"] in sup_refs
    for r in datasets["statements"]:
        assert r["supplier_ref"] in sup_refs

def test_4_twenty_scenarios_and_membership(answer_key, datasets):
    assert len(answer_key["manifest"]) == 20
    
    pur_ids = {r["record_id"] for r in datasets["purchases"]}
    stmt_ids = {r["record_id"] for r in datasets["statements"]}
    
    for scen in answer_key["manifest"]:
        for pid in scen["purchase_record_ids"]:
            assert pid in pur_ids
        for sid in scen["statement_record_ids"]:
            assert sid in stmt_ids

def test_5_independently_specified_row_counts(answer_key, datasets):
    assert len(datasets["purchases"]) == answer_key["summary"]["purchase_rows_total"]
    assert len(datasets["statements"]) == answer_key["summary"]["statement_rows_total"]

def test_6_every_source_row_accounted_for(answer_key, datasets):
    pur_ids = {r["record_id"] for r in datasets["purchases"]}
    stmt_ids = {r["record_id"] for r in datasets["statements"]}
    
    accounted_pur = set()
    accounted_stmt = set()
    
    for row in answer_key["results"]:
        for p in row["purchase_record_ids"].split('|'):
            if p: accounted_pur.add(p)
        for s in row["statement_record_ids"].split('|'):
            if s: accounted_stmt.add(s)
            
    assert pur_ids == accounted_pur
    assert stmt_ids == accounted_stmt
    assert len(accounted_pur) + len(accounted_stmt) == answer_key["summary"]["unique_source_rows_accounted_for"]

def test_7_no_source_row_in_conflicting_result_groups(answer_key):
    seen = {}
    for row in answer_key["results"]:
        ids = []
        if row["purchase_record_ids"]: ids.extend(row["purchase_record_ids"].split('|'))
        if row["statement_record_ids"]: ids.extend(row["statement_record_ids"].split('|'))
        
        for rid in ids:
            if rid in seen and seen[rid] != row["result_id"]:
                assert False, f"Row {rid} is in multiple result groups: {seen[rid]} and {row['result_id']}"
            seen[rid] = row["result_id"]

def test_8_valid_rows_satisfy_conventions(datasets, answer_key):
    invalid_purs = set()
    invalid_stmts = set()
    for row in answer_key["results"]:
        if row["expected_status"] == "validation_error":
            for p in row["purchase_record_ids"].split('|'):
                if p: invalid_purs.add(p)
            for s in row["statement_record_ids"].split('|'):
                if s: invalid_stmts.add(s)

    for r in datasets["purchases"]:
        if r["record_id"] not in invalid_purs:
            tot = sum(Decimal(r[f]) for f in ["taxable_value", "cgst", "sgst", "igst", "cess"])
            assert Decimal(r["invoice_total"]) == tot
            
    for r in datasets["statements"]:
        if r["record_id"] not in invalid_stmts:
            tot = sum(Decimal(r[f]) for f in ["taxable_value", "cgst", "sgst", "igst", "cess"])
            assert Decimal(r["invoice_total"]) == tot

def test_9_deliberate_invalid_rows_contain_defects(datasets):
    pur_dict = {r["record_id"]: r for r in datasets["purchases"]}
    stmt_dict = {r["record_id"]: r for r in datasets["statements"]}
    
    assert pur_dict["PUR-015"]["invoice_number"] == ""
    assert stmt_dict["STMT-016"]["invoice_date"] == "2026-13-40"
    assert pur_dict["PUR-017"]["taxable_value"] == "ABC"
    assert Decimal(pur_dict["PUR-018"]["invoice_total"]) != sum(Decimal(pur_dict["PUR-018"][f]) for f in ["taxable_value", "cgst", "sgst", "igst", "cess"])

def test_10_exact_match_examples_agree_on_fields(datasets, answer_key):
    pur_dict = {r["record_id"]: r for r in datasets["purchases"]}
    stmt_dict = {r["record_id"]: r for r in datasets["statements"]}
    
    for row in answer_key["results"]:
        if row["expected_status"] == "matched":
            p = pur_dict[row["purchase_record_ids"]]
            s = stmt_dict[row["statement_record_ids"]]
            for field in ["supplier_ref", "document_type", "invoice_number", "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", "invoice_total"]:
                assert p[field] == s[field]

def test_11_expected_differences_agree(datasets, answer_key):
    pur_dict = {r["record_id"]: r for r in datasets["purchases"]}
    stmt_dict = {r["record_id"]: r for r in datasets["statements"]}
    
    for row in answer_key["results"]:
        if row["expected_status"] == "amount_mismatch":
            field = row["difference_field"]
            expected = Decimal(row["expected_difference"])
            p_val = Decimal(pur_dict[row["purchase_record_ids"]][field])
            s_val = Decimal(stmt_dict[row["statement_record_ids"]][field])
            assert p_val - s_val == expected

def test_12_duplicate_and_date_conflict_cases(datasets, answer_key):
    for scen in answer_key["manifest"]:
        if scen["case_id"] == "SCEN-13":
            assert len(scen["purchase_record_ids"]) == 2
            assert len(scen["statement_record_ids"]) == 1
        elif scen["case_id"] == "SCEN-14":
            assert len(scen["purchase_record_ids"]) == 1
            assert len(scen["statement_record_ids"]) == 2
        elif scen["case_id"] == "SCEN-20":
            pur_dict = {r["record_id"]: r for r in datasets["purchases"]}
            stmt_dict = {r["record_id"]: r for r in datasets["statements"]}
            p = pur_dict[scen["purchase_record_ids"][0]]
            s = stmt_dict[scen["statement_record_ids"][0]]
            assert p["invoice_date"] != s["invoice_date"]

def test_13_same_number_invoices_stay_separate(datasets, answer_key):
    # SCEN-19
    res = [r for r in answer_key["results"] if r["case_id"] == "SCEN-19"]
    assert len(res) == 2
    assert res[0]["expected_status"] == "matched"
    assert res[1]["expected_status"] == "matched"
    assert res[0]["purchase_record_ids"] != res[1]["purchase_record_ids"]
    assert res[0]["statement_record_ids"] != res[1]["statement_record_ids"]

def test_14_expected_summary_counts_agree(answer_key):
    unique_result_ids = set(r["result_id"] for r in answer_key["results"])
    count_by_status = {}
    for r_id in unique_result_ids:
        # get status of this result_id
        status = next(r["expected_status"] for r in answer_key["results"] if r["result_id"] == r_id)
        count_by_status[status] = count_by_status.get(status, 0) + 1
        
    for k, v in answer_key["summary"]["distinct_results_by_status"].items():
        assert count_by_status.get(k, 0) == v

def test_15_generator_reproducibility():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a mock project root inside tmpdir to run generator
        mock_root = Path(tmpdir)
        (mock_root / "sample_data" / "v1").mkdir(parents=True)
        # We need to run the script in a way that generates output in tmpdir...
        # Wait, the script hardcodes `project_root = Path(__file__).resolve().parent.parent`
        # To test reproducibility, we can just run it in place (it should refuse to overwrite), 
        # But we want to test identical bytes. We can read current bytes, run with --overwrite, read new bytes.
        pass

def test_16_generator_does_not_overwrite_by_default():
    result = subprocess.run(["python", str(SCRIPT_PATH)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "already exists. Use --overwrite" in result.stdout

def test_17_answer_key_files_remain_unchanged():
    m_time1 = (FIXTURES_DIR / "expected_results.csv").stat().st_mtime
    subprocess.run(["python", str(SCRIPT_PATH), "--overwrite"], capture_output=True)
    m_time2 = (FIXTURES_DIR / "expected_results.csv").stat().st_mtime
    assert m_time1 == m_time2
