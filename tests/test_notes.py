"""Credit and debit notes, hand-computed (synthetic data). Amounts in files stay positive; the document type carries
the sign: a credit note subtracts, a debit note adds."""
from backend.gst_copilot.calculation import compute
from backend.gst_copilot.gstr1 import build
from backend.gst_copilot.models import SourceRow, ValidatedInvoice
from backend.gst_copilot.sales import HEADERS, HEADERS_V2, parse_sales, summarize
from backend.gst_copilot.validation import validate_row

V2 = ','.join(HEADERS_V2) + '\n' + '\n'.join([
    # invoice 1000 + 90 + 90
    'N-1,invoice,registered,DEMO-C1,INV-1,2026-08-02,domestic,DEMO-S1,1000.00,90.00,90.00,0.00,0.00,1180.00,Boxes,00DDDDD3333D1Z3,00,18,4819,NOS,100',
    # credit note against it: 200 + 18 + 18
    'N-2,credit_note,registered,DEMO-C1,CN-1,2026-08-10,domestic,DEMO-S1,200.00,18.00,18.00,0.00,0.00,236.00,Return,00DDDDD3333D1Z3,00,18,4819,NOS,20',
    # debit note, inter-state: 100 + 18 IGST
    'N-3,debit_note,registered,DEMO-C2,DN-1,2026-08-12,domestic,DEMO-S2,100.00,0.00,0.00,18.00,0.00,118.00,Extra freight,00EEEEE4444E1Z4,01,18,9965,NOS,1',
    # credit note to an unregistered customer: left out of GSTR-1 with a warning, but still reduces the totals
    'N-4,credit_note,unregistered,DEMO-C3,CN-2,2026-08-15,domestic,DEMO-S1,50.00,4.50,4.50,0.00,0.00,59.00,Discount,,00,18,4819,NOS,5',
]) + '\n'


def test_sales_v2_accepts_notes_and_signs_the_totals():
    rows = parse_sales(V2.encode(), '2026-08')
    assert [r['validation_status'] for r in rows] == ['ready'] * 4
    for r in rows: r['decision'] = 'reviewed'
    totals = summarize(rows)['included_totals']
    # 1000 - 200 + 100 - 50 = 850; CGST 90 - 18 - 4.50 = 67.50; IGST 18; total 1180 - 236 + 118 - 59 = 1003
    assert totals == {'taxable_value': '850.00', 'cgst': '67.50', 'sgst': '67.50', 'igst': '18.00', 'cess': '0.00', 'invoice_total': '1003.00'}


def test_sales_v1_still_treats_notes_as_unsupported():
    v1 = ','.join(HEADERS) + '\nX-1,credit_note,registered,DEMO-C1,CN-1,2026-08-10,domestic,DEMO-S1,200.00,18.00,18.00,0.00,0.00,236.00,Return\n'
    assert parse_sales(v1.encode(), '2026-08')[0]['validation_status'] == 'unsupported'


def test_engine_subtracts_credit_notes_and_adds_debit_notes():
    output = [{'ref': 'N-1', 'cgst': '90.00', 'sgst': '90.00'}, {'ref': 'N-2', 'document_type': 'credit_note', 'cgst': '18.00', 'sgst': '18.00'},
              {'ref': 'N-3', 'document_type': 'debit_note', 'igst': '18.00'}]
    itc = [{'ref': 'R-1', 'cgst': '40.00', 'sgst': '40.00'}, {'ref': 'R-2', 'document_type': 'credit_note', 'cgst': '5.00', 'sgst': '5.00'}]
    heads = compute(output, itc, [])['heads']
    assert (heads['cgst']['output_tax'], heads['cgst']['itc_claimed'], heads['cgst']['net']) == ('72.00', '35.00', '37.00')
    assert (heads['igst']['output_tax'], heads['igst']['net']) == ('18.00', '18.00')


def test_gstr1_reports_registered_notes_in_cdnr():
    rows = [r['raw_data'] for r in parse_sales(V2.encode(), '2026-08')]
    doc, warnings = build(rows, '00AAAAA0000A1Z0', '2026-08')
    assert [i['inum'] for c in doc['b2b'] for i in c['inv']] == ['INV-1']
    assert doc['cdnr'] == [
        {'ctin': '00DDDDD3333D1Z3', 'nt': [{'ntty': 'C', 'nt_num': 'CN-1', 'nt_dt': '10-08-2026', 'val': 236.0, 'pos': '00', 'rchrg': 'N', 'inv_typ': 'R',
                                            'itms': [{'num': 1, 'itm_det': {'txval': 200.0, 'rt': 18.0, 'iamt': 0.0, 'camt': 18.0, 'samt': 18.0, 'csamt': 0.0}}]}]},
        {'ctin': '00EEEEE4444E1Z4', 'nt': [{'ntty': 'D', 'nt_num': 'DN-1', 'nt_dt': '12-08-2026', 'val': 118.0, 'pos': '01', 'rchrg': 'N', 'inv_typ': 'R',
                                            'itms': [{'num': 1, 'itm_det': {'txval': 100.0, 'rt': 18.0, 'iamt': 18.0, 'camt': 0.0, 'samt': 0.0, 'csamt': 0.0}}]}]}]
    assert doc['b2cs'] == []  # the unregistered credit note is not netted silently
    assert any('CN-2' in w and 'unregistered' in w for w in warnings)
    assert [h['txval'] for h in doc['hsn']['data']] == [1000.0]  # notes stay out of HSN, with a warning
    assert sum('not included in the HSN summary' in w for w in warnings) == 2


def test_purchase_validation_accepts_notes():
    row = {'record_id': 'P-1', 'document_type': 'credit_note', 'supplier_ref': '00BBBBB1111B1Z1', 'invoice_number': 'CN-1', 'invoice_date': '2026-08-20',
           'taxable_value': '100.00', 'cgst': '0.00', 'sgst': '0.00', 'igst': '18.00', 'cess': '0.00', 'invoice_total': '118.00'}
    assert isinstance(validate_row(SourceRow('purchase', 'p.csv', 2, row), set()), ValidatedInvoice)
    assert not isinstance(validate_row(SourceRow('purchase', 'p.csv', 2, row | {'document_type': 'refund'}), set()), ValidatedInvoice)


def test_itc_suggestion_includes_purchase_credit_notes():
    from backend.gst_copilot.assist import itc_suggestions
    rows = [{'result_id': s, 'status': s, 'decision': 'undecided', 'document_type': 'credit_note'} for s in ('matched', 'books_only', 'amount_mismatch', 'duplicate_candidate')]
    got = {s['result_id']: s['decision'] for s in itc_suggestions(rows)}
    assert got == {'matched': 'claim', 'books_only': 'not_claimed', 'amount_mismatch': 'not_claimed', 'duplicate_candidate': 'not_claimed'}
    assert all('reversal' in s['reason'] for s in itc_suggestions(rows) if s['status'] in ('books_only', 'amount_mismatch'))
    assert itc_suggestions([{'result_id': 'x', 'status': 'books_only', 'decision': 'undecided'}])[0]['decision'] == 'deferred'  # invoices unchanged
