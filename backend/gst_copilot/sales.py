"""Synthetic sales contract v1: source checks and Decimal totals, no tax inference."""
import csv
import io
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from .validation import parse_decimal

VERSION = 'sales-v1'
AMOUNTS = ('taxable_value','cgst','sgst','igst','cess','invoice_total')
HEADERS = 'record_id document_type customer_type customer_ref invoice_number invoice_date supply_scope place_of_supply taxable_value cgst sgst igst cess invoice_total description'.split()
MAX_BYTES = 5 * 1024 * 1024

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
        if set(headers) != set(HEADERS): raise ValueError('Sales headers must exactly match the documented template')
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
        if d['document_type'] != 'invoice': issues.append('unsupported_document')
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
            for key in AMOUNTS: totals[key] += parse_decimal(row['raw_data'][key])
        else: counts['pending'] += 1
    return dict(counts, included_totals={k:format(v,'.2f') for k,v in totals.items()})
