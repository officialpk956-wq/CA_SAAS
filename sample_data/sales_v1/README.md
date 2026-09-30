# Synthetic sales fixtures v1

Fictional rows only. Not a GST portal export or filing template. No CA validation.

The 19 scenarios and exact CSV contract are in [Phase 4B plan](../../doc/plans/2026-09-14-phase4b-sales-v1.md). Customer and place references are fictional. Row numbers include the header; duplicate record IDs intentionally require row-number identity in the oracle. Blank rows are ignored; other malformed rows are retained or rejected at the file boundary as documented.

Regenerate inputs with `python scripts/generate_sales_demo.py --overwrite` from the root. Without the flag existing input is preserved. Generator never calls the validator or writes expected results. The independent handwritten expected results and totals are under tests/fixtures/sales_v1. Ready rows are 2, 3, 4, 5 and 20. Their source totals sum to 2065.00. Totals start at zero in the application until these rows are reviewed.

The formula-like description is intentional; exported workbooks must preserve it as literal text. Original purchase and reconciliation fixtures are separate and unchanged.
