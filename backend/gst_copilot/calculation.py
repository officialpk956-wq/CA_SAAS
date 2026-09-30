"""calc-v1: per-head draft worksheet (Phase 5A). Pure Decimal arithmetic, no set-off, no rounding.

Consumes already-reviewed amounts; it does not decide tax treatment, rates, or ITC eligibility.
"""
from decimal import Decimal

ENGINE_VERSION = 'calc-v1'
HEADS = ('igst', 'cgst', 'sgst', 'cess')
# Adjustment type -> worksheet column it adds to (itc_reversal is subtracted from credit).
ADJUSTMENT_TYPES = {
    'rcm_liability': 'liability_adjustments',
    'other_liability': 'liability_adjustments',
    'itc_reversal': 'itc_reversal',
    'other_credit': 'other_credit',
}
ZERO = Decimal('0.00')

def _amount(value) -> Decimal:
    amount = Decimal(str(value if value not in (None, '') else '0.00'))
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise ValueError(f'Unsupported amount {value!r}')
    return amount

def compute(output_rows, itc_rows, adjustments) -> dict:
    """output_rows/itc_rows: dicts with 'ref' and optional per-head amounts.
    adjustments: dicts with 'ref', 'type', 'head', 'amount' (active only; voids are filtered by the caller)."""
    heads = {h: {k: ZERO for k in ('output_tax', 'liability_adjustments', 'itc_claimed', 'itc_reversal', 'other_credit')} for h in HEADS}
    for row in output_rows:
        for h in HEADS: heads[h]['output_tax'] += _amount(row.get(h))
    for row in itc_rows:
        for h in HEADS: heads[h]['itc_claimed'] += _amount(row.get(h))
    for adj in adjustments:
        if adj['type'] not in ADJUSTMENT_TYPES: raise ValueError(f"Unsupported adjustment type {adj['type']!r}")
        if adj['head'] not in HEADS: raise ValueError(f"Unsupported tax head {adj['head']!r}")
        amount = _amount(adj['amount'])
        heads[adj['head']][ADJUSTMENT_TYPES[adj['type']]] += amount
    lines = {}
    for h, v in heads.items():
        liability = v['output_tax'] + v['liability_adjustments']
        credit = v['itc_claimed'] - v['itc_reversal'] + v['other_credit']
        lines[h] = {k: format(x, '.2f') for k, x in {**v, 'liability': liability, 'credit': credit, 'net': liability - credit}.items()}
    return {
        'engine_version': ENGINE_VERSION,
        'heads': lines,
        'sources': {
            'output': sorted(r['ref'] for r in output_rows),
            'itc': sorted(r['ref'] for r in itc_rows),
            'adjustments': sorted(a['ref'] for a in adjustments),
        },
    }
