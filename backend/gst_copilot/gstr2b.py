"""GSTR-2B JSON (B2B and CDNR sections) -> GST Helper statement CSV.

Built from GSTN's published field names (data.docdata.b2b[].inv[]: ctin, inum, dt DD-MM-YYYY, val, rev, typ,
itcavl, items[]: txval, igst, cgst, sgst, cess; data.docdata.cdnr[].nt[]: ctin, ntnum, typ C/D, suptyp, dt, val, items[]). NOT yet validated against a real portal download: test with an
authorised sample before relying on it. Amounts are parsed as exact decimals (never floats). Nothing is dropped
silently: every invoice is either converted or listed with the reason it was not.
"""
import csv
import io
import json
from decimal import Decimal, InvalidOperation

HEADERS = ['record_id', 'document_type', 'supplier_ref', 'invoice_number', 'invoice_date', 'taxable_value', 'cgst', 'sgst', 'igst', 'cess', 'invoice_total']
TAXES = ('txval', 'cgst', 'sgst', 'igst', 'cess')
MAX_BYTES = 5 * 1024 * 1024

def _money(v) -> str:
    try: d = Decimal(str(v if v not in (None, '') else '0'))
    except InvalidOperation: raise ValueError(f'not a number: {v!r}')
    if not d.is_finite(): raise ValueError(f'not a finite number: {v!r}')
    return format(d.quantize(Decimal('0.01')), '.2f')

def _iso(dmy: str) -> str:
    parts = str(dmy).split('-')
    if len(parts) != 3 or len(parts[2]) != 4: return str(dmy)  # left as-is; normal validation reports the bad date
    d, m, y = parts
    return f'{y}-{m.zfill(2)}-{d.zfill(2)}'

def convert(content: bytes, period_code: str) -> tuple[bytes, dict]:
    if len(content) > MAX_BYTES: raise ValueError('GSTR-2B file exceeds 5 MiB')
    try: doc = json.loads(content.decode('utf-8-sig'), parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError): raise ValueError('Not a readable JSON file')
    root = doc.get('data', doc) if isinstance(doc, dict) else {}
    docdata = root.get('docdata') if isinstance(root, dict) else None
    if not isinstance(docdata, dict): raise ValueError('No data.docdata section: this does not look like a GSTR-2B JSON download')
    y, m = period_code.split('-')
    rtnprd = str(root.get('rtnprd', ''))
    if rtnprd and rtnprd != f'{m}{y}': raise ValueError(f'This GSTR-2B is for {rtnprd[:2]}/{rtnprd[2:]}, not {m}/{y}')
    rows, skipped, itc_unavailable = [], [], []
    # b2b: inv[] with inum and typ R (regular); cdnr: nt[] with ntnum, typ C (credit) / D (debit) and suptyp R.
    sections = (('b2b', 'inv', 'inum'), ('cdnr', 'nt', 'ntnum'))
    for section, key, number in sections:
        for supplier in docdata.get(section) or []:
            ctin = str(supplier.get('ctin', '')).strip()
            for inv in supplier.get(key) or []:
                ref = f"{ctin} {inv.get(number, '?')}"
                typ, rev = str(inv.get('typ', 'R')).upper(), str(inv.get('rev', 'N')).upper()
                if rev == 'Y': skipped.append({'invoice': ref, 'reason': 'reverse charge (rev=Y): handle as a reverse-charge adjustment'}); continue
                if section == 'b2b':
                    if typ != 'R': skipped.append({'invoice': ref, 'reason': f'invoice type {typ} is not supported (only regular, R)'}); continue
                    document_type = 'invoice'
                else:
                    suptyp = str(inv.get('suptyp', 'R')).upper()
                    if typ not in ('C', 'D') or suptyp != 'R': skipped.append({'invoice': ref, 'reason': f'note type {typ}/{suptyp} is not supported (only regular credit C or debit D notes)'}); continue
                    document_type = 'credit_note' if typ == 'C' else 'debit_note'
                try:
                    items = inv.get('items') or [inv]  # some downloads carry amounts on the document itself
                    sums = {k: sum((Decimal(_money(it.get(k))) for it in items), Decimal('0.00')) for k in TAXES}
                    total = _money(inv.get('val'))
                except ValueError as exc:
                    skipped.append({'invoice': ref, 'reason': f'amount {exc}'}); continue
                n = len(rows) + 1
                rows.append([f'2B-{n:04d}', document_type, ctin, str(inv.get(number, '')), _iso(inv.get('dt', '')),
                             format(sums['txval'], '.2f'), format(sums['cgst'], '.2f'), format(sums['sgst'], '.2f'), format(sums['igst'], '.2f'), format(sums['cess'], '.2f'), total])
                if str(inv.get('itcavl', 'Y')).upper() == 'N':
                    itc_unavailable.append({'record_id': f'2B-{n:04d}', 'invoice': ref, 'reason': str(inv.get('rsn') or 'itcavl = N')})
    for section in ('cdnra', 'b2ba', 'isd', 'impg', 'impgsez'):
        count = sum(len(s.get('nt') or s.get('inv') or [None]) for s in (docdata.get(section) or []))
        if count: skipped.append({'invoice': f'{section} section', 'reason': f'{count} document(s) in section "{section}" are not supported yet'})
    if not rows: raise ValueError('No regular B2B invoices or credit/debit notes found to import' + (f' ({len(skipped)} skipped)' if skipped else ''))
    out = io.StringIO(); w = csv.writer(out, lineterminator='\n'); w.writerow(HEADERS); w.writerows(rows)
    return out.getvalue().encode(), {'converted': len(rows), 'skipped': skipped, 'itc_unavailable': itc_unavailable,
                                     'notice': 'Converted from the GSTR-2B B2B and CDNR sections using GSTN\'s published field names; not yet validated against a real portal file.'}
