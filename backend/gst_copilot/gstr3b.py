"""Arrange a worksheet into GSTR-3B-style tables (3.1, 4, 6.1). Presentation only; no new arithmetic beyond sums.

The mapping of worksheet figures to form tables is a draft for CA review. Rows the demo does not capture are
reported as not captured (None), never as zero.
"""
from decimal import Decimal

HEADS = ('igst', 'cgst', 'sgst', 'cess')
VERSION = 'gstr3b-view-v1'

def _row(label, taxable, heads):
    return {'label': label, 'taxable_value': taxable, **{h: heads.get(h) if heads is not None else None for h in HEADS}}

def summary(worksheet: dict | None, setoff: dict | None, outward_taxable: str, rcm: dict) -> dict:
    """worksheet: calc-v1 result; setoff: setoff section; outward_taxable: sum of included sales taxable values;
    rcm: reverse-charge liability adjustments per head (strings)."""
    if not worksheet: return {'version': VERSION, 'status': 'not_available', 'reason': 'The worksheet has a calculation error.'}
    w = worksheet['heads']
    zero = '0.00'
    t31 = [
        _row('(a) Outward taxable supplies (other than zero rated, nil rated and exempted)', outward_taxable, {h: w[h]['output_tax'] for h in HEADS}),
        _row('(b) Outward taxable supplies (zero rated)', None, None),
        _row('(c) Other outward supplies (nil rated, exempted)', None, None),
        _row('(d) Inward supplies (liable to reverse charge)', None, {h: rcm.get(h, zero) for h in HEADS}),
        _row('(e) Non-GST outward supplies', None, None),
    ]
    other_credit = {h: w[h]['other_credit'] for h in HEADS}
    t4 = [
        _row('(A)(1)–(4) Import, reverse charge, ISD credit', None, None),
        _row('(A)(5) All other ITC (claimed exact matches)', None, {h: w[h]['itc_claimed'] for h in HEADS}),
        _row('Other credit adjustments (placement for CA review)', None, other_credit),
        _row('(B) ITC reversed', None, {h: w[h]['itc_reversal'] for h in HEADS}),
        _row('(C) Net ITC available (A) − (B), excluding opening balance', None,
             {h: format(Decimal(w[h]['itc_claimed']) + Decimal(other_credit[h]) - Decimal(w[h]['itc_reversal']), '.2f') for h in HEADS}),
    ]
    payment = None
    if setoff and setoff.get('status') == 'computed':
        used = {(u['credit_head'], u['liability_head']): u['amount'] for u in setoff['utilisation']}
        payment = []
        for lh in HEADS:
            through = {ch: used.get((ch, lh), zero) for ch in HEADS}
            payment.append({'head': lh, 'tax_payable': setoff['heads'][lh]['liability'], 'paid_through_itc': through, 'paid_in_cash': setoff['heads'][lh]['cash'],
                            'interest': None, 'late_fee': None})
    return {
        'version': VERSION, 'status': 'available',
        'table_3_1': t31, 'table_4': t4,
        'table_6_1': payment,
        'table_6_1_note': None if payment is not None else (setoff or {}).get('reason', 'Set-off not computed.'),
        'notice': 'Draft layout after the GSTR-3B tables; mapping of worksheet figures to tables is for CA review. Rows marked not captured are outside this demo. Interest and late fee are not computed. Not a return.',
    }
