"""setoff-v1 (Phase 5B): apply credit against liability in a CA-confirmed order, then round cash if configured.

No utilisation order or rounding rule is built in. Both arrive as CA-confirmed legal rules; without them the
caller reports set-off as not computed. Pure Decimal arithmetic, no database.
"""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

VERSION = 'setoff-v1'
HEADS = ('igst', 'cgst', 'sgst', 'cess')
DIRECTIONS = {'half_up': ROUND_HALF_UP, 'up': ROUND_CEILING, 'down': ROUND_FLOOR}
ZERO = Decimal('0.00')

def parse_steps(lines) -> list[tuple[str, str]]:
    """'IGST>CGST' lines -> [('igst','cgst'), ...]; order preserved. Raises ValueError with a readable message."""
    steps = []
    for raw in lines:
        line = str(raw).strip()
        if not line: continue
        parts = [p.strip().lower() for p in line.replace('→', '>').split('>')]
        if len(parts) != 2 or any(p not in HEADS for p in parts):
            raise ValueError(f'"{line}" must look like IGST>CGST using IGST, CGST, SGST or CESS')
        if tuple(parts) in steps: raise ValueError(f'"{line}" appears twice')
        steps.append(tuple(parts))
    if not steps: raise ValueError('Enter at least one step, one per line, e.g. IGST>IGST')
    return steps

def _round(amount: Decimal, multiple: Decimal, direction: str) -> Decimal:
    return ((amount / multiple).quantize(Decimal('1'), rounding=DIRECTIONS[direction]) * multiple).quantize(Decimal('0.01'))

def setoff(liability: dict, credit: dict, steps, rounding: dict | None) -> dict:
    """liability/credit: per-head decimal strings (from the worksheet). steps: [(credit_head, liability_head)].
    rounding: {'multiple': '1.00', 'direction': 'half_up'|'up'|'down'} or None (no rounding)."""
    owed = {h: Decimal(liability.get(h, '0.00')) for h in HEADS}
    left = {h: Decimal(credit.get(h, '0.00')) for h in HEADS}
    negative = [h.upper() for h in HEADS if left[h] < 0 or owed[h] < 0]
    if negative:
        return {'version': VERSION, 'status': 'not_computed',
                'reason': f"Negative credit or liability for {', '.join(negative)} (e.g. reversal larger than credit). The CA must advise before set-off."}
    used = []
    for ch, lh in steps:
        amount = min(left[ch], owed[lh])
        if amount > 0:
            left[ch] -= amount; owed[lh] -= amount
            used.append({'credit_head': ch, 'liability_head': lh, 'amount': format(amount, '.2f')})
    cash = {h: _round(owed[h], Decimal(rounding['multiple']), rounding['direction']) if rounding and owed[h] > 0 else owed[h] for h in HEADS}
    return {
        'version': VERSION, 'status': 'computed', 'utilisation': used,
        'heads': {h: {'liability': format(Decimal(liability.get(h, '0.00')), '.2f'), 'credit': format(Decimal(credit.get(h, '0.00')), '.2f'),
                      'cash_before_rounding': format(owed[h], '.2f'), 'cash': format(cash[h], '.2f'),
                      'rounding_difference': format(cash[h] - owed[h], '.2f'), 'carry_forward': format(left[h], '.2f')} for h in HEADS},
        'total_cash_before_rounding': format(sum(owed.values(), ZERO), '.2f'),
        'total_cash': format(sum(cash.values(), ZERO), '.2f'),
        'total_carry_forward': format(sum(left.values(), ZERO), '.2f'),
    }
