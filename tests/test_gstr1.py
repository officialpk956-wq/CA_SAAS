import json
from pathlib import Path
from backend.gst_copilot.gstr1 import build
from backend.gst_copilot.sales import contract_version, parse_sales

SAMPLE = Path('sample_data/sales_v2/sales_register.csv').read_bytes()
EXPECTED = json.loads(Path('tests/fixtures/sales_v2/expected_gstr1.json').read_text(encoding='utf-8'))

def test_sales_v2_validates_supplied_gstr1_fields():
    assert contract_version(SAMPLE) == 'sales-v2'
    rows = {r['raw_data']['record_id']: r for r in parse_sales(SAMPLE, '2026-08')}
    assert [k for k, r in rows.items() if r['validation_status'] == 'ready'] == [f'S2-00{i}' for i in range(1, 7)]
    assert 'invalid_customer_gstin' in rows['S2-007']['issues'] and 'gstin_on_unregistered' in rows['S2-008']['issues']
    assert contract_version(Path('sample_data/sales_v1/sales_register.csv').read_bytes()) == 'sales-v1'

def test_gstr1_matches_hand_computed_draft():
    ready = [r['raw_data'] for r in parse_sales(SAMPLE, '2026-08') if r['validation_status'] == 'ready']
    doc, warnings = build(ready, EXPECTED['gstin'], '2026-08')
    for key in ('gstin', 'fp', 'b2b', 'b2cs', 'hsn'):
        assert doc[key] == EXPECTED[key], key
    assert any('INV-206' in w and 'B2CL' in w for w in warnings)
    assert any('doc_issue' in w for w in warnings)
    # Section totals agree with the source rows (every rupee lands in exactly one of b2b / b2cs).
    txval = sum(i['itms'][0]['itm_det']['txval'] for c in doc['b2b'] for i in c['inv']) + sum(g['txval'] for g in doc['b2cs'])
    assert round(txval, 2) == round(sum(float(r['taxable_value']) for r in ready), 2) == round(sum(h['txval'] for h in doc['hsn']['data']), 2)
