"""Excel from persisted views; all source text is written as literal text."""

import json
import re

from openpyxl import Workbook

from openpyxl.styles import Font, PatternFill



def sanitize_value(value):

    if value is None:

        return ""

    if isinstance(value, (dict, list)):

        value = json.dumps(value, ensure_ascii=False)

    value = str(value)
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]", lambda match: "\\u%04x" % ord(match.group()), value)

    # Plain signed decimals (e.g. "-200.00") are data, not formulas; keep them unprefixed.
    if value.lstrip().startswith(('=', '+', '-', '@')) and not re.fullmatch(r"-\d+(\.\d+)?", value):

        return "'" + value

    return value



def generate_excel_export(data, export_path):

    wb = Workbook()

    wb.remove(wb.active)

    def sheet(name, headers, rows):

        ws = wb.create_sheet(name)

        ws.append(headers)

        for row in rows:

            ws.append([sanitize_value(v) for v in row])

        ws.freeze_panes = "A2"

        ws.auto_filter.ref = ws.dimensions

        for cell in ws[1]:

            cell.font = Font(bold=True, color="FFFFFF")

            cell.fill = PatternFill('solid', fgColor='164E63')

        for col in ws.columns:

            ws.column_dimensions[col[0].column_letter].width = min(60, max(18, max(len(str(c.value or '')) for c in col) + 2))

        return ws

    sheet('Metadata', ['Key', 'Value'], [('Notice', 'Synthetic demo — not for filing. Reconciliation does not establish tax eligibility.'), *[(k, data.get(k, '')) for k in ['run_id', 'client_id', 'period_id', 'purchase_batch_id', 'statement_batch_id', 'export_timestamp', 'review_cutoff']], ('Amounts', 'Decimal strings; purchase minus statement. Source identifiers preserved as text.')])

    summary = []

    for key, value in (data.get('summary_data') or {}).items():

        if isinstance(value, dict):

            summary.extend((f'{key}.{k}', v) for k, v in value.items())

        else:

            summary.append((key, value))

    sheet('Summary', ['Metric', 'Count'], summary)

    results = data.get('results', [])

    sheet('Reconciliation Results', ['Result ID', 'Finding', 'Reason', 'Purchase records', 'Statement records', 'Review state'], [(r['result_id'], r['status'], r['reason'], '|'.join(r['purchase_record_ids']), '|'.join(r['statement_record_ids']), r['review_status']) for r in results])

    sheet('Field Differences', ['Result ID', 'Field', 'Purchase minus statement'], [(r['result_id'], field, value) for r in results for field, value in r['differences'].items()])

    fields = ['record_id', 'supplier_ref', 'document_type', 'invoice_number', 'invoice_date', 'taxable_value', 'cgst', 'sgst', 'igst', 'cess', 'invoice_total', 'description']

    for name, source in [('Purchase Records', 'purchases'), ('Statement Records', 'statements')]:

        sheet(name, ['Source row', 'Valid', *fields], [(r['row_number'], r['is_valid'], *[r['raw_data'].get(f, '') for f in fields]) for r in data.get(source, [])])

    sheet('Validation Issues', ['Source', 'Source row', 'Record ID', 'Issue'], [(source, r['row_number'], r['record_id'], issue) for source in ['purchases', 'statements'] for r in data.get(source, []) for issue in r['issues']])

    sheet('Review History', ['Result ID', 'Decision', 'Note', 'Actor', 'Timestamp'], [(r['result_id'], e['decision'], e['note'], e['actor_id'], e['created_at']) for r in results for e in r['history']])

    wb.save(export_path)

    return export_path

