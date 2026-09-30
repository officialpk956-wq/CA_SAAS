# Synthetic Data Fixtures for GST Copilot MVP (v1)

## Purpose
These datasets provide a complete, standalone, deterministic test environment for the GST Copilot purchase-register reconciliation engine. They contain purely synthetic, fictional records for testing exact invoice matching, exception detection, and duplicate handling.

## Files
- `client_profile.csv`: Stable fictional client context.
- `suppliers.csv`: Fictional suppliers used across the records.
- `purchase_register.csv`: 20 synthetic purchase records.
- `gstr2b_demo.csv`: 20 synthetic statement records.

## Formats
- **Encoding**: UTF-8 CSV.
- **Dates**: `YYYY-MM-DD` format.
- **Amounts**: Decimal numbers as text, 2 decimal places, no commas/symbols (e.g. `1000.00`).
- **Missing taxes**: Expressed as explicit `0.00` rather than empty strings.
- **Identifiers**: Record IDs (`PUR-xxx`, `STMT-xxx`), supplier refs (`DEMO-SUP-xxx`), and client IDs (`C-xxx`). The identifiers are expressly DEMO-prefixed to ensure they cannot be confused with real GSTINs.

## Statement Limitations
The `gstr2b_demo.csv` file represents a heavily simplified tabular extract. It is **not** a byte-for-byte representation of an official GST Portal JSON/Excel export. It lacks sections for amendments, reverse charge, and document typing found in real government formats. 

## Scenario List
Exactly 20 scenarios are implemented (see `tests/fixtures/reconciliation_v1/scenario_manifest.json` for details):
1-5: Exact matches
6-7: Books only
8-9: Statement only
10: Amount mismatch (Taxable Value)
11: Amount mismatch (Tax amounts differ)
12: Amount mismatch (Equal combined tax, different components)
13: Duplicate in purchases
14: Duplicate in statement
15: Missing invoice number (validation error)
16: Invalid date (validation error)
17: Nonnumeric amount (validation error)
18: Inconsistent total (validation error)
19: Same invoice number used by different suppliers (both match correctly)
20: Date conflict

## Data Generation
To reproduce these datasets:
```bash
python scripts/generate_synthetic_data.py --overwrite
```
Note: without `--overwrite`, the script will refuse to alter existing files.

## Running Tests
To verify data integrity against the independent answer key:
```bash
pytest tests/test_synthetic_fixtures.py -v
```

## Independent Answer Key
The expected results (`scenario_manifest.json`, `expected_results.csv`, `expected_summary.json`) are maintained completely independently from the data generation logic. This guarantees that we aren't "testing the generator against itself." The answer keys represent the exact mathematical ground truth expected from the reconciliation engine.

## Known Exclusions
- No credit notes, debit notes, or amendments.
- No eligibility/ITC claims.
- No reverse charge mechanisms (RCM) or imports.
- No fuzzy matching logic or automatic rounding tolerances.

## Usage in Reconciliation
The future reconciliation engine will ingest these four CSVs and should perfectly reproduce the statuses, matched groups, and numerical differences defined in `tests/fixtures/reconciliation_v1/expected_results.csv`.
