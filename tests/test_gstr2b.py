import csv
import io
import json
from pathlib import Path
import pytest
from backend.gst_copilot.gstr2b import convert

SAMPLE = Path('tests/fixtures/gstr2b_v1/sample_gstr2b.json').read_bytes()

def rows(out: bytes):
    return list(csv.DictReader(io.StringIO(out.decode())))

def test_converts_regular_b2b_invoices_with_exact_amounts():
    out, summary = convert(SAMPLE, '2026-08')
    r = rows(out)
    assert [x['record_id'] for x in r] == ['2B-0001', '2B-0002', '2B-0003']
    assert r[0] == {'record_id': '2B-0001', 'document_type': 'invoice', 'supplier_ref': '00BBBBB1111B1Z1', 'invoice_number': 'SUP1/001', 'invoice_date': '2026-08-03',
                    'taxable_value': '2000.00', 'cgst': '180.00', 'sgst': '180.00', 'igst': '0.00', 'cess': '0.00', 'invoice_total': '2360.00'}
    assert (r[1]['invoice_date'], r[1]['taxable_value'], r[1]['igst'], r[1]['invoice_total']) == ('2026-08-07', '100.10', '18.00', '118.10')
    assert (r[2]['invoice_number'], r[2]['igst'], r[2]['cess'], r[2]['invoice_total']) == ('0043', '120.00', '1.00', '1121.00')
    assert summary['converted'] == 3
    reasons = ' | '.join(s['reason'] for s in summary['skipped'])
    assert len(summary['skipped']) == 3 and 'reverse charge' in reasons and 'SEWP' in reasons and 'cdnr' in reasons
    assert summary['itc_unavailable'] == [{'record_id': '2B-0002', 'invoice': '00BBBBB1111B1Z1 SUP1/002', 'reason': 'P'}]

def test_refuses_wrong_period_and_non_2b_files():
    with pytest.raises(ValueError, match='not 09/2026'):
        convert(SAMPLE, '2026-09')
    with pytest.raises(ValueError, match='docdata'):
        convert(json.dumps({'hello': 'world'}).encode(), '2026-08')
    with pytest.raises(ValueError, match='readable JSON'):
        convert(b'\xff\xfe not json', '2026-08')

def test_bad_amount_is_listed_not_guessed():
    doc = json.loads(SAMPLE)
    doc['data']['docdata']['b2b'][0]['inv'][0]['items'][0]['txval'] = 'abc'
    out, summary = convert(json.dumps(doc).encode(), '2026-08')
    assert [x['invoice_number'] for x in rows(out)] == ['SUP1/002', '0043']
    assert any('SUP1/001' in s['invoice'] and 'not a number' in s['reason'] for s in summary['skipped'])
