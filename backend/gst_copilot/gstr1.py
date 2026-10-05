"""GSTR-1 draft JSON (b2b, cdnr, b2cs, hsn) from reviewed sales-v2 rows.

Field names follow GSTN's published GSTR-1 JSON (b2b: ctin, inv[inum, idt DD-MM-YYYY, val, pos, rchrg, inv_typ,
itms[num, itm_det{txval, rt, iamt, camt, samt, csamt}]]; b2cs: sply_ty, pos, typ, rt, txval, iamt, camt, samt,
csamt; cdnr: ctin, nt[ntty C/D, nt_num, nt_dt, val, pos, rchrg, inv_typ, itms]; hsn.data[]). NOT validated against the offline tool or portal: open it in the GSTN offline tool and have a
CA review it before any use. All values are supplied by the user; nothing is inferred. Sections that need rules or
data this demo does not hold (B2CL threshold, document series, notes to unregistered customers, the current HSN table split) are
reported as warnings, never guessed.
"""
from collections import defaultdict
from decimal import Decimal

VERSION = 'GSTHELPER-GSTR1-DRAFT-1'
D = Decimal

def _num(d: Decimal) -> float:
    # Two-decimal values round-trip exactly through float repr (e.g. 1180.0, 112.5).
    return float(d.quantize(D('0.01')))

def _idt(iso: str) -> str:
    y, m, d = iso.split('-'); return f'{d}-{m}-{y}'

def build(rows: list[dict], gstin: str, period_code: str) -> tuple[dict, list[str]]:
    """rows: raw_data dicts of reviewed, ready sales-v2 rows."""
    y, m = period_code.split('-')
    warnings = []
    b2b = defaultdict(list); cdnr = defaultdict(list); b2cs = defaultdict(lambda: defaultdict(lambda: D('0.00'))); hsn = {}
    for r in rows:
        amt = {k: D(r[k]) for k in ('taxable_value', 'igst', 'cgst', 'sgst', 'cess', 'invoice_total')}
        rt = D(r['rate'])
        if r['document_type'] != 'invoice':
            # Registered-customer notes go to cdnr with positive values and ntty C/D. Notes to unregistered customers
            # (B2CS netting or cdnur) and the HSN treatment of notes need a CA decision, so they are left out.
            if r['customer_type'] != 'registered':
                warnings.append(f"{r['invoice_number']}: {r['document_type'].replace('_', ' ')} to an unregistered customer left out; decide B2CS netting or CDNUR with a CA."); continue
            cdnr[r['customer_gstin'].strip()].append({'ntty': 'C' if r['document_type'] == 'credit_note' else 'D', 'nt_num': r['invoice_number'], 'nt_dt': _idt(r['invoice_date']),
                'val': _num(amt['invoice_total']), 'pos': r['pos_state_code'], 'rchrg': 'N', 'inv_typ': 'R', 'itms': [{'num': 1, 'itm_det': {'txval': _num(amt['taxable_value']),
                'rt': _num(rt), 'iamt': _num(amt['igst']), 'camt': _num(amt['cgst']), 'samt': _num(amt['sgst']), 'csamt': _num(amt['cess'])}}]})
            warnings.append(f"{r['invoice_number']}: {r['document_type'].replace('_', ' ')} is not included in the HSN summary; check the HSN treatment of notes with a CA.")
            continue
        if r['customer_type'] == 'registered':
            b2b[r['customer_gstin'].strip()].append({'inum': r['invoice_number'], 'idt': _idt(r['invoice_date']), 'val': _num(amt['invoice_total']), 'pos': r['pos_state_code'],
                'rchrg': 'N', 'inv_typ': 'R', 'itms': [{'num': 1, 'itm_det': {'txval': _num(amt['taxable_value']), 'rt': _num(rt), 'iamt': _num(amt['igst']),
                'camt': _num(amt['cgst']), 'samt': _num(amt['sgst']), 'csamt': _num(amt['cess'])}}]})
            if len(r['invoice_number']) > 16: warnings.append(f"{r['invoice_number']}: invoice number longer than 16 characters.")
        else:
            # Inter- vs intra-state read from the supplied amounts (IGST present), not inferred from states.
            sply = 'INTER' if amt['igst'] > 0 else 'INTRA'
            if sply == 'INTER': warnings.append(f"{r['invoice_number']}: inter-state B2C invoice kept in B2CS; B2CL split needs a CA-confirmed threshold (not configured).")
            g = b2cs[(sply, r['pos_state_code'], rt)]
            for src, dst in (('taxable_value', 'txval'), ('igst', 'iamt'), ('cgst', 'camt'), ('sgst', 'samt'), ('cess', 'csamt')): g[dst] += amt[src]
        h = hsn.setdefault((r['hsn_code'], r['uqc'], rt), defaultdict(lambda: D('0')))
        h['qty'] += D(r['quantity'])
        for src, dst in (('taxable_value', 'txval'), ('igst', 'iamt'), ('cgst', 'camt'), ('sgst', 'samt'), ('cess', 'csamt')): h[dst] += amt[src]
    doc = {
        'gstin': gstin, 'fp': f'{m}{y}', 'version': VERSION,
        'b2b': [{'ctin': ctin, 'inv': sorted(invs, key=lambda i: i['inum'])} for ctin, invs in sorted(b2b.items())],
        **({'cdnr': [{'ctin': ctin, 'nt': sorted(nts, key=lambda n: n['nt_num'])} for ctin, nts in sorted(cdnr.items())]} if cdnr else {}),
        'b2cs': [{'sply_ty': s, 'pos': pos, 'typ': 'OE', 'rt': _num(rt), **{k: _num(g[k]) for k in ('txval', 'iamt', 'camt', 'samt', 'csamt')}} for (s, pos, rt), g in sorted(b2cs.items())],
        'hsn': {'data': [{'num': n, 'hsn_sc': code, 'desc': '', 'uqc': uqc, 'qty': float(h['qty']), 'rt': _num(rt), **{k: _num(h[k]) for k in ('txval', 'iamt', 'camt', 'samt', 'csamt')}}
                         for n, ((code, uqc, rt), h) in enumerate(sorted(hsn.items()), 1)]},
    }
    warnings += ['doc_issue (document series) not produced: series and cancellations are not captured.',
                 'Exports, B2CL and amended documents are not supported in this draft.',
                 'HSN summary uses a single table; check whether the current portal schema needs separate B2B/B2C HSN tables.']
    return doc, warnings
