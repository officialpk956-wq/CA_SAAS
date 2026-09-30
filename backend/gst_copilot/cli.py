import sys
import argparse
from pathlib import Path
from .parser import parse_purchases, parse_statements, parse_suppliers, ParserError
from .validation import validate_datasets
from .reconciliation import reconcile
from .reporting import serialize_results, serialize_summary

def main():
    parser = argparse.ArgumentParser(description="GST Helper Exact Reconciliation Engine")
    parser.add_argument("--purchases", required=True, help="Path to purchase_register.csv")
    parser.add_argument("--statements", required=True, help="Path to gstr2b_demo.csv")
    parser.add_argument("--suppliers", required=True, help="Path to suppliers.csv")
    parser.add_argument("--outdir", required=True, help="Output directory for reports")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing reports")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    results_path = outdir / "reconciliation_results.json"
    summary_path = outdir / "reconciliation_summary.json"

    print("Note: The formats and records are synthetic demo inputs.")

    # Check overwrite protection
    if not args.overwrite:
        if results_path.exists() or summary_path.exists():
            print(f"Error: Output files already exist in {outdir}. Use --overwrite to replace them.", file=sys.stderr)
            return 1
            
    # Protect inputs
    input_paths = [Path(args.purchases).resolve(), Path(args.statements).resolve(), Path(args.suppliers).resolve()]
    for p in [results_path.resolve(), summary_path.resolve()]:
        if p in input_paths:
            print(f"Error: Output path {p} would overwrite an input file.", file=sys.stderr)
            return 1

    if not outdir.exists():
        outdir.mkdir(parents=True, exist_ok=True)

    try:
        sup_list = parse_suppliers(args.suppliers)
        pur_rows = parse_purchases(args.purchases)
        stmt_rows = parse_statements(args.statements)
    except ParserError as e:
        print(f"Parsing error: {e}", file=sys.stderr)
        return 1

    try:
        valid_p, valid_s, val_issues = validate_datasets(pur_rows, stmt_rows, sup_list)
    except ValueError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        return 1
        
    results, summary = reconcile(valid_p, valid_s, val_issues, len(pur_rows), len(stmt_rows))

    results_json = serialize_results(results)
    summary_json = serialize_summary(summary)

    # Write output
    with open(results_path, 'w', encoding='utf-8') as f:
        f.write(results_json)
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary_json)
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
