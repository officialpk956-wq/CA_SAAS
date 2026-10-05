import json
from pathlib import Path
import pytest
from backend.gst_copilot.calculation import compute, HEADS

CASES = json.loads(Path('tests/fixtures/calc_v1/cases.json').read_text())['cases']

@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_matches_independent_reference(case):
    result = compute(case['output'], case['itc'], case['adjustments'])
    for head in HEADS:
        for key, value in case['expected'][head].items():
            assert result['heads'][head][key] == value, (head, key)
    assert result['sources']['output'] == sorted(r['ref'] for r in case['output'])
    assert result['sources']['itc'] == sorted(r['ref'] for r in case['itc'])

@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_input_order_does_not_change_result(case):
    forward = compute(case['output'], case['itc'], case['adjustments'])
    backward = compute(case['output'][::-1], case['itc'][::-1], case['adjustments'][::-1])
    assert forward == backward

@pytest.mark.parametrize('bad', ['-1.00', '1.001', 'NaN', 'Infinity', 'abc'])
def test_rejects_unsupported_amounts(bad):
    with pytest.raises(Exception):
        compute([{'ref': 'S1', 'cgst': bad}], [], [])

def test_rejects_unknown_adjustment_type_and_head():
    with pytest.raises(ValueError):
        compute([], [], [{'ref': 'A', 'type': 'interest', 'head': 'igst', 'amount': '1.00'}])
    with pytest.raises(ValueError):
        compute([], [], [{'ref': 'A', 'type': 'rcm_liability', 'head': 'utgst', 'amount': '1.00'}])
