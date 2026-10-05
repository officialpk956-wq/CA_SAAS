import json
from pathlib import Path
import pytest
from backend.gst_copilot.setoff import HEADS, parse_steps, setoff

DATA = json.loads(Path('tests/fixtures/setoff_v1/cases.json').read_text(encoding='utf-8'))
CASES = DATA['cases']

def run(case):
    return setoff(case['liability'], case['credit'], parse_steps(DATA['configs'][case['config']]), case['rounding'])

@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_matches_independent_reference(case):
    out, exp = run(case), case['expected']
    if exp.get('status') == 'not_computed':
        assert out['status'] == 'not_computed' and exp['reason_contains'] in out['reason']
        return
    assert out['status'] == 'computed'
    assert [[u['credit_head'], u['liability_head'], u['amount']] for u in out['utilisation']] == exp['utilisation']
    for h in HEADS:
        assert out['heads'][h]['cash'] == exp['cash'][h], h
        assert out['heads'][h]['carry_forward'] == exp['carry_forward'][h], h
        if 'cash_before_rounding' in exp: assert out['heads'][h]['cash_before_rounding'] == exp['cash_before_rounding'][h], h
    assert out['total_cash'] == exp['total_cash']
    if 'total_cash_before_rounding' in exp: assert out['total_cash_before_rounding'] == exp['total_cash_before_rounding']

@pytest.mark.parametrize('case', [c for c in CASES if 'status' not in c['expected']], ids=lambda c: c['id'])
def test_conservation(case):
    """Every rupee of liability is either paid by credit or left as cash; every rupee of credit is used or carried."""
    out = run(case)
    used = {h: sum(float(u['amount']) for u in out['utilisation'] if u['credit_head'] == h) for h in HEADS}
    paid = {h: sum(float(u['amount']) for u in out['utilisation'] if u['liability_head'] == h) for h in HEADS}
    for h in HEADS:
        head = out['heads'][h]
        assert round(float(head['credit']) - used[h] - float(head['carry_forward']), 2) == 0
        assert round(float(head['liability']) - paid[h] - float(head['cash_before_rounding']), 2) == 0

def test_step_parsing_preserves_order_and_rejects_bad_lines():
    assert parse_steps(['IGST>CGST', ' sgst > igst ', '', 'CESS→CESS']) == [('igst', 'cgst'), ('sgst', 'igst'), ('cess', 'cess')]
    for bad in (['IGST'], ['IGST>UTGST'], ['IGST>CGST>SGST'], ['IGST>CGST', 'igst>cgst'], ['  ']):
        with pytest.raises(ValueError):
            parse_steps(bad)

def test_no_rounding_leaves_paise():
    out = setoff({'cgst': '10.49'}, {}, [('cgst', 'cgst')], None)
    assert out['heads']['cgst']['cash'] == '10.49' and out['heads']['cgst']['rounding_difference'] == '0.00'
