import csv
import sys
import argparse
from pathlib import Path
from decimal import Decimal

def format_amt(val):
    if isinstance(val, str) and not val.replace('.', '', 1).isdigit():
        return val # Pass through invalid strings
    return str(Decimal(str(val)).quantize(Decimal("0.00")))

def calc_tot(taxable, c, s, i, ce):
    return str((Decimal(str(taxable)) + Decimal(str(c)) + Decimal(str(s)) + Decimal(str(i)) + Decimal(str(ce))).quantize(Decimal("0.00")))

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic data for GST Copilot MVP.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "sample_data" / "v1"
    
    if not data_dir.exists():
        data_dir.mkdir(parents=True)

    files_to_write = [
        data_dir / "client_profile.csv",
        data_dir / "suppliers.csv",
        data_dir / "purchase_register.csv",
        data_dir / "gstr2b_demo.csv",
    ]

    if not args.overwrite:
        for f in files_to_write:
            if f.exists():
                print(f"Error: {f.name} already exists. Use --overwrite to replace.")
                return 1

    # Data generation
    client_profile = [{
        "client_id": "C-001",
        "client_name": "Demo Client Limited",
        "registration_ref": "DEMO-REG-001",
        "filing_frequency": "monthly",
        "reporting_period": "2026-08",
        "currency": "INR"
    }]

    suppliers = [
        {"supplier_ref": "DEMO-SUP-001", "supplier_name": "Office Supplies Ltd", "business_category": "Retail"},
        {"supplier_ref": "DEMO-SUP-002", "supplier_name": "Tech Services Inc", "business_category": "IT Services"},
        {"supplier_ref": "DEMO-SUP-003", "supplier_name": "Logistics Co", "business_category": "Transport"},
        {"supplier_ref": "DEMO-SUP-004", "supplier_name": "Cleaners R Us", "business_category": "Maintenance"},
        {"supplier_ref": "DEMO-SUP-005", "supplier_name": "Consultant LLP", "business_category": "Professional"},
    ]

    purchases = []
    statements = []

    def add_pair(scen_type, p_id, s_id, sup, inv, date, taxb, c, s, i, ce, p_overrides=None, s_overrides=None):
        p_row = {
            "record_id": p_id, "document_type": "invoice", "supplier_ref": sup,
            "invoice_number": inv, "invoice_date": date,
            "taxable_value": format_amt(taxb),
            "cgst": format_amt(c), "sgst": format_amt(s), "igst": format_amt(i), "cess": format_amt(ce),
            "invoice_total": calc_tot(taxb, c, s, i, ce), "description": f"Scenario {scen_type}"
        } if p_id else None

        if p_overrides and p_row:
            p_row.update(p_overrides)

        s_row = {
            "record_id": s_id, "document_type": "invoice", "supplier_ref": sup,
            "invoice_number": inv, "invoice_date": date,
            "taxable_value": format_amt(taxb),
            "cgst": format_amt(c), "sgst": format_amt(s), "igst": format_amt(i), "cess": format_amt(ce),
            "invoice_total": calc_tot(taxb, c, s, i, ce)
        } if s_id else None

        if s_overrides and s_row:
            s_row.update(s_overrides)

        if p_row: purchases.append(p_row)
        if s_row: statements.append(s_row)

    # 1-5 Exact matches
    add_pair(1, "PUR-001", "STMT-001", "DEMO-SUP-001", "INV-101", "2026-08-01", 1000, 90, 90, 0, 0)
    add_pair(2, "PUR-002", "STMT-002", "DEMO-SUP-002", "INV-102", "2026-08-02", 2000, 180, 180, 0, 0)
    add_pair(3, "PUR-003", "STMT-003", "DEMO-SUP-003", "INV-103", "2026-08-03", 3000, 0, 0, 360, 0)
    add_pair(4, "PUR-004", "STMT-004", "DEMO-SUP-004", "INV-104", "2026-08-04", 4000, 0, 0, 0, 400)
    add_pair(5, "PUR-005", "STMT-005", "DEMO-SUP-005", "INV-105", "2026-08-05", 5000, 450, 450, 0, 0)

    # 6-7 Books only
    add_pair(6, "PUR-006", None, "DEMO-SUP-001", "INV-106", "2026-08-06", 600, 54, 54, 0, 0)
    add_pair(7, "PUR-007", None, "DEMO-SUP-002", "INV-107", "2026-08-07", 700, 63, 63, 0, 0)

    # 8-9 Statement only
    add_pair(8, None, "STMT-008", "DEMO-SUP-003", "INV-108", "2026-08-08", 800, 0, 0, 144, 0)
    add_pair(9, None, "STMT-009", "DEMO-SUP-004", "INV-109", "2026-08-09", 900, 0, 0, 0, 90)

    # 10 Taxable mismatch
    add_pair(10, "PUR-010", "STMT-010", "DEMO-SUP-001", "INV-110", "2026-08-10", 1000, 90, 90, 0, 0, 
             s_overrides={"taxable_value": format_amt(1200), "invoice_total": calc_tot(1200, 90, 90, 0, 0)})

    # 11 Tax amounts mismatch
    add_pair(11, "PUR-011", "STMT-011", "DEMO-SUP-002", "INV-111", "2026-08-11", 1000, 90, 90, 0, 0,
             s_overrides={"cgst": format_amt(100), "sgst": format_amt(100), "invoice_total": calc_tot(1000, 100, 100, 0, 0)})

    # 12 Tax components mismatch
    add_pair(12, "PUR-012", "STMT-012", "DEMO-SUP-003", "INV-112", "2026-08-12", 2000, 180, 180, 0, 0,
             s_overrides={"cgst": format_amt(0), "sgst": format_amt(0), "igst": format_amt(360), "invoice_total": calc_tot(2000, 0, 0, 360, 0)})

    # 13 Duplicate in purchases
    add_pair(13, "PUR-013A", "STMT-013", "DEMO-SUP-004", "INV-113", "2026-08-13", 1000, 90, 90, 0, 0)
    add_pair(13, "PUR-013B", None, "DEMO-SUP-004", "INV-113", "2026-08-13", 1000, 90, 90, 0, 0)

    # 14 Duplicate in statement
    add_pair(14, "PUR-014", "STMT-014A", "DEMO-SUP-005", "INV-114", "2026-08-14", 2000, 180, 180, 0, 0)
    add_pair(14, None, "STMT-014B", "DEMO-SUP-005", "INV-114", "2026-08-14", 2000, 180, 180, 0, 0)

    # 15 Missing invoice number in purchases
    add_pair(15, "PUR-015", "STMT-015", "DEMO-SUP-001", "INV-115", "2026-08-15", 1000, 90, 90, 0, 0,
             p_overrides={"invoice_number": ""})

    # 16 Invalid date in statement
    add_pair(16, "PUR-016", "STMT-016", "DEMO-SUP-002", "INV-116", "2026-08-16", 1000, 90, 90, 0, 0,
             s_overrides={"invoice_date": "2026-13-40"})

    # 17 Nonnumeric amount in purchases
    add_pair(17, "PUR-017", "STMT-017", "DEMO-SUP-003", "INV-117", "2026-08-17", 1000, 90, 90, 0, 0,
             p_overrides={"taxable_value": "ABC", "invoice_total": "0.00"}) # If taxable is invalid, fallback is often 0 or preserved. 

    # 18 Inconsistent total in purchases
    add_pair(18, "PUR-018", "STMT-018", "DEMO-SUP-004", "INV-118", "2026-08-18", 1000, 90, 90, 0, 0,
             p_overrides={"invoice_total": format_amt(1100)})

    # 19 Different suppliers, same invoice number
    add_pair(19, "PUR-019A", "STMT-019A", "DEMO-SUP-001", "INV-999", "2026-08-19", 1000, 90, 90, 0, 0)
    add_pair(19, "PUR-019B", "STMT-019B", "DEMO-SUP-002", "INV-999", "2026-08-19", 2000, 180, 180, 0, 0)

    # 20 Date conflict
    add_pair(20, "PUR-020", "STMT-020", "DEMO-SUP-005", "INV-120", "2026-08-20", 1000, 90, 90, 0, 0,
             s_overrides={"invoice_date": "2026-08-21"})


    def write_csv(path, data, fields):
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)
        print(f"Wrote {path.name} with {len(data)} rows.")

    write_csv(files_to_write[0], client_profile, ["client_id", "client_name", "registration_ref", "filing_frequency", "reporting_period", "currency"])
    write_csv(files_to_write[1], suppliers, ["supplier_ref", "supplier_name", "business_category"])
    
    pur_fields = ["record_id", "document_type", "supplier_ref", "invoice_number", "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", "invoice_total", "description"]
    write_csv(files_to_write[2], purchases, pur_fields)
    
    stmt_fields = ["record_id", "document_type", "supplier_ref", "invoice_number", "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", "invoice_total"]
    write_csv(files_to_write[3], statements, stmt_fields)

    print("Data generation complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
