"""Synthetic sales contracts v1 and v2: source checks and Decimal totals, no tax inference.

v2 adds the fields a GSTR-1 draft needs, all SUPPLIED by the user, never inferred: customer GSTIN (registered
customers only, GSTIN-shaped), place-of-supply state code, rate, HSN code, unit (UQC) and quantity.
v2 also accepts credit_note and debit_note rows: amounts stay positive and a credit note subtracts from totals."""
import csv
import io
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from .calculation import sign
from .validation import DOCUMENT_TYPES, parse_decimal

VERSION = 'sales-v1'
AMOUNTS = ('taxable_value','cgst','sgst','igst','cess','invoice_total')
HEADERS = 'record_id document_type customer_type customer_ref invoice_number invoice_date supply_scope place_of_supply taxable_value cgst sgst igst cess invoice_total description'.split()
MAX_BYTES = 5 * 1024 * 1024
V2_EXTRA = 'customer_gstin pos_state_code rate hsn_code uqc quantity'.split()
HEADERS_V2 = HEADERS + V2_EXTRA
GSTIN_SHAPE = re.compile(r'\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]')

def contract_version(content: bytes) -> str:
    first = content.decode('utf-8-sig', errors='replace').splitlines()[0] if content else ''
    return 'sales-v2' if set(next(csv.reader([first]), [])) == set(HEADERS_V2) else VERSION

def parse_sales(content: bytes, period: str) -> list[dict]:
    if len(content) > MAX_BYTES: raise ValueError('Sales file exceeds 5 MiB')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', period): raise ValueError('Period must be YYYY-MM')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Sales CSV must be UTF-8') from exc
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text): raise ValueError('CSV contains unsupported control characters')
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    try:
        headers = next(reader, [])
        if len(headers) != len(set(headers)): raise ValueError('Duplicate sales headers')
        if set(headers) not in (set(HEADERS), set(HEADERS_V2)): raise ValueError('Sales headers must exactly match the documented v1 or v2 template')
        v2 = set(headers) == set(HEADERS_V2)
        rows = []
        for number, values in enumerate(reader,2):
            if not values or not any(v.strip() for v in values): continue
            if len(values) != len(headers): raise ValueError(f'Row {number}: column count does not match header')
            if len(rows) >= 10000: raise ValueError('Sales file exceeds 10000 records')
            if any(len(v) > 2000 for v in values): raise ValueError(f'Row {number}: field exceeds 2000 characters')
            rows.append({'row_number':number,'raw_data':dict(zip(headers,values))})
    except csv.Error as exc:
        raise ValueError('Malformed sales CSV') from exc
    if not rows: raise ValueError('Sales CSV contains no records')
    ids = Counter(r['raw_data']['record_id'].strip() for r in rows)
    identities = Counter((r['raw_data']['document_type'].strip(),r['raw_data']['invoice_number'].strip()) for r in rows)
    for row in rows:
        d = row['raw_data']; issues = []
        for key in ('record_id','invoice_number'):
            if not d[key].strip(): issues.append('missing_'+key)
            elif d[key] != d[key].strip(): issues.append('whitespace_'+key)
        # Notes need v2: GSTR-1 reports them separately and v1 has no customer GSTIN to report them against.
        if d['document_type'] not in (DOCUMENT_TYPES if v2 else ('invoice',)): issues.append('unsupported_document')
        if d['supply_scope'] != 'domestic': issues.append('unsupported_scope')
        if d['customer_type'] not in ('registered','unregistered'): issues.append('invalid_customer_type')
        if not re.fullmatch(r'DEMO-[A-Za-z0-9-]+',d['customer_ref']): issues.append('invalid_customer_ref')
        if not d['place_of_supply'].strip(): issues.append('missing_place_of_supply')
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',d['invoice_date']): raise ValueError()
            date.fromisoformat(d['invoice_date'])
            if d['invoice_date'][:7] != period: issues.append('wrong_period')
        except ValueError: issues.append('invalid_date')
        amounts = {}
        for key in AMOUNTS:
            try: amounts[key] = parse_decimal(d[key])
            except ValueError: issues.append('invalid_'+key)
        if len(amounts) == len(AMOUNTS) and amounts['invoice_total'] != sum((amounts[k] for k in AMOUNTS[:-1]), Decimal('0.00')):
            issues.append('total_mismatch')
        if v2:
            gstin = d['customer_gstin'].strip()
            if d['customer_type'] == 'registered' and not GSTIN_SHAPE.fullmatch(gstin): issues.append('invalid_customer_gstin')
            if d['customer_type'] == 'unregistered' and gstin: issues.append('gstin_on_unregistered')
            if not re.fullmatch(r'\d{2}', d['pos_state_code']): issues.append('invalid_pos_state_code')
            if not re.fullmatch(r'\d{1,2}(\.\d{1,2})?', d['rate']) or Decimal(d['rate']) > 100: issues.append('invalid_rate')
            if not re.fullmatch(r'\d{4,8}', d['hsn_code']): issues.append('invalid_hsn_code')
            if not re.fullmatch(r'[A-Z]{3}', d['uqc']): issues.append('invalid_uqc')
            if not re.fullmatch(r'\d{1,12}(\.\d{1,3})?', d['quantity']): issues.append('invalid_quantity')
        if d['record_id'].strip() and ids[d['record_id'].strip()] > 1: issues.append('duplicate_record_id')
        if d['invoice_number'].strip() and identities[(d['document_type'].strip(),d['invoice_number'].strip())] > 1: issues.append('duplicate_invoice')
        row['issues'] = issues
        row['validation_status'] = ('duplicate' if any(i.startswith('duplicate') for i in issues) else 'unsupported' if any(i.startswith('unsupported') for i in issues) else 'invalid' if issues else 'ready')
    return rows

def summarize(rows: list[dict]) -> dict:
    counts = dict.fromkeys(('source_rows','ready','invalid','duplicate','unsupported','included','excluded','pending'),0)
    totals = {k:Decimal('0.00') for k in AMOUNTS}
    for row in rows:
        counts['source_rows'] += 1
        counts[row['validation_status']] += 1
        decision = row.get('decision','unresolved')
        if decision == 'excluded': counts['excluded'] += 1
        elif decision == 'reviewed' and row['validation_status'] == 'ready':
            counts['included'] += 1
            for key in AMOUNTS: totals[key] += sign(row['raw_data']) * parse_decimal(row['raw_data'][key])
        else: counts['pending'] += 1
    return dict(counts, included_totals={k:format(v,'.2f') for k,v in totals.items()})
