"""Deterministic assistants ("agents") for GST Helper.

Every function here is pure: it reads records the application already holds and returns suggestions,
explanations or drafts. Nothing here writes data, computes tax, or decides a treatment; the API applies
a suggestion only when a person accepts it through the normal, validated endpoint.
No language model is used. A model can later replace wording or scoring behind the same shapes.
"""
import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

TAX = ('cgst', 'sgst', 'igst', 'cess')
AMOUNTS = ('taxable_value', *TAX, 'invoice_total')

def money(value) -> Decimal:
    try: return Decimal(str(value or '0')).quantize(Decimal('0.01'))
    except InvalidOperation: return Decimal('0.00')

def tax_of(record) -> Decimal:
    return sum((money(record.get(h)) for h in TAX), Decimal('0.00'))

def fmt(value: Decimal) -> str:
    return format(value, ',.2f')

# --- 1. Invoice-number normalisation (used by the investigator) -------------------------------

def normalize_invoice(value: str) -> str:
    """INV/0018, inv-18 and INV 18 all become INV18. Digit groups lose leading zeros, separators vanish."""
    no_zeros = re.sub(r'\d+', lambda m: str(int(m.group())), value or '')
    return re.sub(r'[^0-9A-Za-z]', '', no_zeros).upper()

def _days_apart(a: str, b: str):
    try: return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except (TypeError, ValueError): return None

# --- 2. ITC pre-fill --------------------------------------------------------------------------

ITC_RULES = {
    'matched': ('claim', 'Exact match with the supplier statement.'),
    'books_only': ('deferred', 'Supplier has not reported this invoice yet; re-check next period.'),
    'amount_mismatch': ('not_claimed', 'Amounts differ from the statement; claim after the supplier confirms.'),
    'date_conflict': ('not_claimed', 'Invoice dates differ; confirm the correct date first.'),
    'duplicate_candidate': ('not_claimed', 'Duplicate entries must be resolved before any claim.'),
    'statement_only': ('not_claimed', 'Not in your books; record the purchase first if it is genuine.'),
    'validation_error': ('not_claimed', 'Source row failed validation.'),
}

# A purchase credit note lowers credit. 'claim' on a note means "include it in the worksheet", which reduces credit;
# leaving it out would overstate credit. CA to confirm.
# Only exact matches can be included (calc-v1), so an unmatched note is pointed at a manual ITC reversal adjustment.
CREDIT_NOTE_INCLUDE = {
    'matched': ('claim', 'Credit note matches the statement: include it so claimed credit is reduced.'),
    'books_only': ('not_claimed', 'Credit note not on the statement yet. If it is genuine, record the reduction as an ITC reversal adjustment; CA to confirm.'),
    'amount_mismatch': ('not_claimed', 'Credit note amounts differ from the statement. Confirm with the supplier and record the reduction as an ITC reversal adjustment; CA to confirm.'),
}

def itc_suggestions(results):
    """results: [{result_id, status, decision, document_type?}] -> suggestion per undecided result."""
    out = []
    for r in results:
        if r['decision'] != 'undecided': continue
        decision, reason = ITC_RULES.get(r['status'], ('not_claimed', 'No rule for this finding; review manually.'))
        if r.get('document_type') == 'credit_note' and r['status'] in CREDIT_NOTE_INCLUDE:
            decision, reason = CREDIT_NOTE_INCLUDE[r['status']]
        out.append({'result_id': r['result_id'], 'status': r['status'], 'decision': decision, 'reason': reason})
    return out

# --- 3. Exception investigator ----------------------------------------------------------------

def _describe(record):
    return f"{record['record_id']} · {record['supplier_ref']} · {record['invoice_number']} · {record['invoice_date']} · total {fmt(money(record['invoice_total']))}"

def _field_diffs(a, b):
    return {f: format(money(a.get(f)) - money(b.get(f)), '.2f') for f in AMOUNTS if money(a.get(f)) != money(b.get(f))}

def investigate(result, own_records, unmatched_other_side):
    """Explain one reconciliation finding and look for likely counterparts.

    result: {status, purchase_record_ids, statement_record_ids, differences}
    own_records: the records named by the result (dicts with record fields and 'side').
    unmatched_other_side: records from the opposite side that are themselves unmatched (books_only /
    statement_only), the only place a missed pairing can hide.
    """
    status = result['status']; findings = []; candidates = []
    if status in ('books_only', 'statement_only'):
        me = own_records[0]
        other = 'statement' if status == 'books_only' else 'purchase books'
        findings.append(f"{_describe(me)} has no exact counterpart in the {other}.")
        key = normalize_invoice(me['invoice_number'])
        for rec in unmatched_other_side:
            reasons = []
            same_supplier = rec['supplier_ref'] == me['supplier_ref']
            if normalize_invoice(rec['invoice_number']) == key: reasons.append(f"invoice number {rec['invoice_number']!r} matches {me['invoice_number']!r} once punctuation and leading zeros are ignored")
            if money(rec['invoice_total']) == money(me['invoice_total']): reasons.append('same invoice total')
            days = _days_apart(rec['invoice_date'], me['invoice_date'])
            if days is not None and days <= 5 and reasons: reasons.append('same date' if days == 0 else f'dates {days} day(s) apart')
            strong = any('invoice number' in r for r in reasons) or (same_supplier and 'same invoice total' in reasons)
            if strong:
                if not same_supplier: reasons.append(f"but supplier differs ({rec['supplier_ref']} vs {me['supplier_ref']})")
                candidates.append({'record': rec, 'reasons': reasons, 'differences': _field_diffs(me, rec) if me['side'] == 'purchase' else _field_diffs(rec, me)})
        if candidates:
            findings.append(f"{len(candidates)} likely counterpart(s) found; the engine did not pair them because the identity differs. Check the invoice copy before explaining.")
        elif status == 'books_only':
            findings.append('No likely counterpart found. The supplier has probably not filed this invoice yet.')
        else:
            findings.append('No likely counterpart found. This purchase may be missing from your books.')
    elif status == 'amount_mismatch':
        diffs = {k: money(v) for k, v in (result.get('differences') or {}).items()}
        for field, d in diffs.items():
            findings.append(f"{field.replace('_', ' ')} differs by {fmt(d)} (purchase minus statement).")
        tax_diffs = {h: diffs.get(h, Decimal('0')) for h in TAX}
        if any(tax_diffs.values()) and sum(tax_diffs.values()) == 0:
            findings.append('Total tax is the same but split differently across heads — possibly intra-state vs inter-state treatment. Confirm place of supply.')
        elif 'taxable_value' in diffs and not any(tax_diffs.values()):
            findings.append('Taxable value differs but tax is identical — likely a keying error in one of the two records.')
    elif status == 'date_conflict':
        a, b = own_records[0], own_records[-1]
        days = _days_apart(a['invoice_date'], b['invoice_date'])
        findings.append(f"Same supplier and invoice number, but dates differ ({a['invoice_date']} vs {b['invoice_date']}{f', {days} day(s) apart' if days is not None else ''}).")
        findings.append('Usually the invoice date was keyed differently in one record; amounts can still be compared once the date is confirmed.')
    elif status == 'duplicate_candidate':
        findings.append(f"{len(own_records)} records share the same supplier, document type and invoice number.")
        amounts = {tuple(money(r.get(f)) for f in AMOUNTS) for r in own_records if r['side'] == 'purchase'}
        if sum(r['side'] == 'purchase' for r in own_records) > 1 and len(amounts) == 1:
            findings.append('The purchase entries are identical — this looks like the same invoice entered twice in the books.')
    elif status == 'validation_error':
        findings.append('The source row failed validation and was excluded from matching. Correct it in a new import version.')
    else:
        findings.append('Exact match — nothing to investigate.')
    note = ' '.join(findings)[:1900]
    return {'summary': findings[0] if findings else '', 'findings': findings, 'candidates': candidates, 'suggested_note': note}

# --- 4. Column mapper -------------------------------------------------------------------------

TEMPLATES = {
    'purchase': ['record_id', 'document_type', 'supplier_ref', 'invoice_number', 'invoice_date', 'taxable_value', 'cgst', 'sgst', 'igst', 'cess', 'invoice_total', 'description'],
    'statement': ['record_id', 'document_type', 'supplier_ref', 'invoice_number', 'invoice_date', 'taxable_value', 'cgst', 'sgst', 'igst', 'cess', 'invoice_total'],
    'sales': ['record_id', 'document_type', 'customer_type', 'customer_ref', 'invoice_number', 'invoice_date', 'supply_scope', 'place_of_supply', 'taxable_value', 'cgst', 'sgst', 'igst', 'cess', 'invoice_total', 'description'],
}
OPTIONAL = {'description'}
# Common spellings seen in accounting exports, normalised (lower-case, letters and digits only).
ALIASES = {
    'record_id': ['recordid', 'id', 'srno', 'slno', 'serialno', 'sno', 'rowid', 'entryno', 'lineno'],
    'document_type': ['documenttype', 'doctype', 'vouchertype', 'vchtype', 'type', 'documentkind'],
    'supplier_ref': ['supplierref', 'supplier', 'suppliercode', 'supplierid', 'vendor', 'vendorcode', 'vendorid', 'partycode', 'party', 'partyname'],
    'customer_ref': ['customerref', 'customer', 'customercode', 'customerid', 'buyer', 'buyercode', 'party', 'partycode', 'partyname'],
    'customer_type': ['customertype', 'buyertype', 'registrationtype', 'partytype'],
    'invoice_number': ['invoicenumber', 'invoiceno', 'invno', 'billno', 'billnumber', 'voucherno', 'vouchernumber', 'documentnumber', 'docno', 'invoiceref'],
    'invoice_date': ['invoicedate', 'date', 'billdate', 'invdate', 'documentdate', 'voucherdate', 'docdate'],
    'supply_scope': ['supplyscope', 'scope', 'supplytype'],
    'place_of_supply': ['placeofsupply', 'pos', 'supplystate', 'statecode'],
    'taxable_value': ['taxablevalue', 'taxable', 'taxableamount', 'assessablevalue', 'taxableamt', 'value'],
    'cgst': ['cgst', 'cgstamount', 'cgstamt', 'centraltax', 'centraltaxamount'],
    'sgst': ['sgst', 'sgstamount', 'sgstamt', 'statetax', 'stateuttax', 'sgstutgst', 'utgst'],
    'igst': ['igst', 'igstamount', 'igstamt', 'integratedtax', 'integratedtaxamount'],
    'cess': ['cess', 'cessamount', 'cessamt', 'compensationcess'],
    'invoice_total': ['invoicetotal', 'total', 'invoicevalue', 'totalamount', 'grandtotal', 'totalinvoicevalue', 'amount'],
    'description': ['description', 'narration', 'particulars', 'item', 'itemdescription', 'details', 'remarks'],
}

def _norm(header: str) -> str:
    return re.sub(r'[^0-9a-z]', '', header.lower())

def read_headers(content: bytes):
    text = content.decode('utf-8-sig')
    return next(csv.reader(io.StringIO(text)), [])

def propose_mapping(headers, template):
    """Return {target: source header or None} using exact names first, then known aliases (first alias wins)."""
    fields = TEMPLATES[template]; normed = {h: _norm(h) for h in headers}; used = set(); mapping = {}
    for field in fields:  # exact template names first
        mapping[field] = next((h for h in headers if normed[h] == _norm(field) and h not in used), None)
        if mapping[field]: used.add(mapping[field])
    for field in fields:
        if mapping[field]: continue
        for alias in ALIASES.get(field, []):
            hit = next((h for h in headers if normed[h] == alias and h not in used), None)
            if hit: mapping[field] = hit; used.add(hit); break
    missing = [f for f in fields if not mapping[f] and f not in OPTIONAL]
    return {'template': template, 'mapping': mapping, 'unused_headers': [h for h in headers if h not in used], 'missing_required': missing}

def apply_mapping(content: bytes, template, mapping):
    """Rewrite a CSV into the template layout. Values are copied verbatim — nothing is cleaned or guessed,
    so the normal validation still reports every problem in the source."""
    fields = TEMPLATES[template]
    unknown = set(mapping) - set(fields)
    if unknown: raise ValueError(f'Unknown template fields: {sorted(unknown)}')
    missing = [f for f in fields if f not in OPTIONAL and not mapping.get(f)]
    if missing: raise ValueError(f'Map every required field first: {missing}')
    chosen = [s for s in mapping.values() if s]
    if len(chosen) != len(set(chosen)): raise ValueError('Each source column can map to only one field')
    reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
    absent = [s for s in chosen if s not in (reader.fieldnames or [])]
    if absent: raise ValueError(f'Columns not found in file: {absent}')
    out = io.StringIO(); writer = csv.writer(out, lineterminator='\n'); writer.writerow(fields)
    for row in reader:
        writer.writerow([(row.get(mapping[f]) or '') if mapping.get(f) else '' for f in fields])
    return out.getvalue().encode('utf-8')

# --- 5. Supplier follow-up drafts -------------------------------------------------------------

def supplier_followups(items, supplier_names, client_name, period_code):
    """items: [{supplier_ref, kind: 'missing'|'mismatch', record, differences}] -> one draft per supplier."""
    grouped = {}
    for item in items: grouped.setdefault(item['supplier_ref'], []).append(item)
    drafts = []
    for ref, entries in sorted(grouped.items()):
        name = supplier_names.get(ref, ref)
        lines = []
        for e in entries:
            r = e['record']
            if e['kind'] == 'missing':
                lines.append(f"- Invoice {r['invoice_number']} dated {r['invoice_date']}, value {fmt(money(r['invoice_total']))} (tax {fmt(tax_of(r))}) — not visible in our {period_code} statement.")
            else:
                diffs = ', '.join(f"{k.replace('_', ' ')} {fmt(money(v))}" for k, v in e['differences'].items())
                lines.append(f"- Invoice {r['invoice_number']} dated {r['invoice_date']} — amounts differ from your filing ({diffs}, our books minus statement).")
        at_risk = sum((tax_of(e['record']) for e in entries if e['kind'] == 'missing'), Decimal('0.00'))
        body = (f"Dear {name} team,\n\nWhile reconciling {client_name}'s purchases for {period_code}, we found the following:\n" + '\n'.join(lines) +
                "\n\nCould you please check and file or amend these at the earliest, or share the correct invoice copy?\n\nThank you.")
        drafts.append({'supplier_ref': ref, 'supplier_name': name, 'invoices': len(entries), 'credit_at_risk': format(at_risk, '.2f'), 'message': body})
    return drafts

# --- 6. Knowledge rule drafting ---------------------------------------------------------------

MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'], 1)}

def _month_after(word: str, text: str):
    """'from Aug 2026' / 'from 2026-08' style month after a keyword, as YYYY-MM."""
    m = re.search(rf'{word}\s+(\d{{4}})-(\d{{2}})', text)
    if m: return f'{m.group(1)}-{m.group(2)}'
    m = re.search(rf'{word}\s+(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?([a-z]+)\s+(\d{{4}})', text)
    month = next((n for name, n in MONTHS.items() if m and len(m.group(1)) >= 3 and name.startswith(m.group(1))), None)
    return f'{m.group(2)}-{month:02d}' if month else None

def parse_rule_note(note: str):
    """Pull structured slots out of a CA's note. Anything not found is listed in 'missing' for the person to fill.

    A note with no amount and no adjustment wording but a checking verb ("confirm", "ensure", "remind"...)
    becomes a reminder: a checklist item that must be acknowledged before approval."""
    text = note.lower()
    frequency = 'quarterly' if re.search(r'quarter', text) else 'one_time' if re.search(r'one[- ]?time|\bonce\b|only (in|for)', text) else 'monthly'
    effective_to = _month_after('(?:until|till|up to)', text)
    if re.search(r'reverse charge|\brcm\b|unregistered (landlord|supplier|vendor)', text): kind = 'rcm_liability'
    elif re.search(r'revers(e|al) (of )?(itc|credit)|itc reversal|exempt', text): kind = 'itc_reversal'
    elif re.search(r'\bcredit\b', text): kind = 'other_credit'
    elif re.search(r'liabilit|payable|output tax', text): kind = 'other_liability'
    else: kind = None
    head = next((h for h in ('igst', 'cgst', 'sgst', 'cess') if re.search(rf'\b{h}\b', text)), None)
    amount = None
    m = re.search(r'(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)', text) or re.search(r'\b(\d[\d,]*\.\d{2})\b', text)
    if m: amount = format(money(m.group(1).replace(',', '')), '.2f')
    effective = _month_after('from', text) or _month_after(r'(?:only (?:in|for)|\bin)', text)
    if not kind and not amount and re.search(r'confirm|ensure|check|remind|verify|before (filing|approval)|make sure|\bask\b', text):
        return {'rule_kind': 'reminder', 'adjustment_type': None, 'tax_head': None, 'amount': None, 'frequency': frequency,
                'effective_from': effective, 'effective_to': effective_to, 'missing': [] if effective else ['effective_from']}
    fields = {'adjustment_type': kind, 'tax_head': head, 'amount': amount, 'effective_from': effective}
    return {'rule_kind': 'adjustment', **fields, 'frequency': frequency, 'effective_to': effective_to, 'missing': [k for k, v in fields.items() if not v]}

# --- 7. Morning brief -------------------------------------------------------------------------

def morning_brief(board_rows, recent_events, credit_at_risk: Decimal):
    """Plain sentences built only from Board cells and audit rows. Each sentence carries a link."""
    streams = ('sales', 'purchases', 'worksheet')
    blocked = [(r, s) for r in board_rows for s in streams if r[s]['tone'] == 'blocked']
    action = [(r, s) for r in board_rows for s in streams if r[s]['tone'] == 'action']
    done = [r for r in board_rows if all(r[s]['tone'] == 'done' for s in streams)]
    href = lambda r, s: f"/periods/{r['period_id']}/{r[s]['target']}"
    out = []
    if not board_rows:
        return [{'text': 'No periods yet. Add a client and a period to start the month.', 'href': '/clients', 'tone': 'waiting'}]
    for r, s in blocked[:3]:
        out.append({'text': f"{r['client_name']} ({r['period_code']}): {r[s]['label']} — fix this first.", 'href': href(r, s), 'tone': 'blocked'})
    for r, s in action[:4]:
        out.append({'text': f"{r['client_name']} ({r['period_code']}) needs you: {r[s]['label']}.", 'href': href(r, s), 'tone': 'action'})
    if len(action) > 4:
        out.append({'text': f'{len(action) - 4} more item(s) need attention on the board below.', 'href': '/', 'tone': 'action'})
    if credit_at_risk > 0:
        out.append({'text': f'₹{fmt(credit_at_risk)} of input tax credit is waiting on suppliers or unclaimed — see the savings finder.', 'href': '/#savings', 'tone': 'action'})
    counts = {}
    for e in recent_events: counts[e['action']] = counts.get(e['action'], 0) + 1
    changes = [f"{n} {label}" for key, label in (('tax_draft_approved', 'approval(s)'), ('tax_approval_reopened', 'reopening(s)'), ('filing_evidence_recorded', 'filing reference(s)'), ('import_committed', 'import(s) committed')) if (n := counts.get(key))]
    if changes:
        out.append({'text': 'In the last 24 hours: ' + ', '.join(changes) + '.', 'href': '/history', 'tone': 'waiting'})
    out.append({'text': f"{len(done)} of {len(board_rows)} period(s) are complete.", 'href': '/', 'tone': 'done'})
    return out

# --- 8. Ask the ledger ------------------------------------------------------------------------

INTENTS = [
    ('blockers', r'block|pending|stuck|left to do|what.*(remaining|missing)|can.?t approve|cannot approve'),
    ('changes', r'chang|after approval|out of date|stale|since'),
    ('who', r'\bwho\b|approved by|reopened by|filed by|when was'),
    ('savings', r'sav|at risk|unclaimed|lose|lost|recover'),
    ('suppliers', r'supplier|vendor|follow.?up'),
    # Broadest pattern last, so specific questions ('how much credit is at risk') are not read as 'explain a figure'.
    ('explain_head', r'\b(why|how|explain|what makes)\b.*\b(igst|cgst|sgst|cess|net|liability|credit)\b|\b(igst|cgst|sgst|cess)\b.*\b(net|liability|credit)\b'),
]
SUGGESTED = ['Why is CGST net what it is?', 'What is blocking approval?', 'What changed after approval?', 'Who approved this period?', 'How much credit is at risk?', 'Which suppliers should we follow up?']

def ask(question: str, ctx):
    """Answer from a fixed set of question types using only this period's records. Abstains otherwise.

    ctx: {period_code, draft (view or None), blockers, events, savings, followups}
    """
    q = question.lower().strip()
    intent = next((name for name, pattern in INTENTS if re.search(pattern, q)), None)
    cite = []
    if intent == 'explain_head':
        draft = ctx.get('draft')
        if not draft or not draft['payload'].get('worksheet'):
            return {'intent': intent, 'answer': 'There is no saved draft for this period yet, so there are no figures to explain. Save a draft snapshot first.', 'citations': []}
        head = next((h for h in ('igst', 'cgst', 'sgst', 'cess') if h in q), 'cgst')
        line = draft['payload']['worksheet']['heads'][head]; inputs = draft['payload']['inputs']
        out_rows = [r for r in inputs['output'] if money(r.get(head))]
        itc_rows = [r for r in inputs['itc'] if money(r.get(head))]
        adjs = [a for a in inputs['adjustments'] if a['head'] == head]
        answer = (f"{head.upper()} net is {line['net']} in draft {draft['id'][:8].upper()} ({draft['state'].replace('_', ' ')}). "
                  f"Liability {line['liability']} = output tax {line['output_tax']} from {len(out_rows)} reviewed sales row(s) + liability adjustments {line['liability_adjustments']}. "
                  f"Credit {line['credit']} = ITC claimed {line['itc_claimed']} from {len(itc_rows)} exact match(es) − reversals {line['itc_reversal']} + other credit {line['other_credit']}. "
                  f"Net = liability − credit. No set-off or rounding is applied.")
        cite = ([{'label': f"Sales {r['ref']} ({head.upper()} {r[head]})", 'ref': r['ref']} for r in out_rows[:8]] +
                [{'label': f"ITC {r['purchase_record_id']} ({head.upper()} {r[head]})", 'ref': r['ref']} for r in itc_rows[:8]] +
                [{'label': f"Adjustment {a['type'].replace('_', ' ')} {a['amount']}: {a['note']}", 'ref': a['ref']} for a in adjs])
        return {'intent': intent, 'answer': answer, 'citations': cite}
    if intent == 'blockers':
        blockers = ctx.get('blockers')
        if blockers is None: return {'intent': intent, 'answer': 'Choose the sales version and reconciliation run first; blockers depend on those inputs.', 'citations': []}
        if not blockers: return {'intent': intent, 'answer': 'Nothing is blocking approval for the selected inputs.', 'citations': []}
        return {'intent': intent, 'answer': f'{len(blockers)} thing(s) block approval: ' + ' '.join(blockers), 'citations': [{'label': b, 'ref': 'blocker'} for b in blockers]}
    events = ctx.get('events', [])
    if intent == 'changes':
        approvals = [e for e in events if e['action'] == 'tax_draft_approved']
        if not approvals: return {'intent': intent, 'answer': 'This period has not been approved yet, so nothing has changed after approval.', 'citations': []}
        last = max(approvals, key=lambda e: e['created_at'])
        later = [e for e in events if e['created_at'] > last['created_at']]
        if not later: return {'intent': intent, 'answer': f"Nothing has changed since the last approval on {last['created_at'][:16].replace('T', ' ')}.", 'citations': [{'label': 'Approval', 'ref': last['id']}]}
        return {'intent': intent, 'answer': f"{len(later)} action(s) since the last approval ({last['created_at'][:16].replace('T', ' ')}): " + '; '.join(f"{e['action'].replace('_', ' ')} ({e['summary'] or '—'})" for e in sorted(later, key=lambda e: e['created_at'])[:6]) + '.',
                'citations': [{'label': f"{e['action'].replace('_', ' ')} · {e['created_at'][:16].replace('T', ' ')} · {e['actor'] or 'system'}", 'ref': e['id']} for e in later[:10]]}
    if intent == 'who':
        wanted = [e for e in events if e['action'] in ('tax_draft_approved', 'tax_approval_reopened', 'filing_evidence_recorded')]
        if not wanted: return {'intent': intent, 'answer': 'No approval, reopening or filing reference has been recorded for this period.', 'citations': []}
        return {'intent': intent, 'answer': ' '.join(f"{e['action'].replace('_', ' ').capitalize()} by {e['actor'] or 'system'} on {e['created_at'][:16].replace('T', ' ')}." for e in sorted(wanted, key=lambda e: e['created_at'])),
                'citations': [{'label': e['summary'] or e['action'], 'ref': e['id']} for e in wanted]}
    if intent == 'savings':
        s = ctx.get('savings') or {'total': '0.00', 'items': []}
        if not s['items']: return {'intent': intent, 'answer': 'No credit at risk was found for this period.', 'citations': []}
        return {'intent': intent, 'answer': f"₹{s['total']} across {len(s['items'])} item(s): " + '; '.join(f"{i['title']} ₹{i['amount']}" for i in s['items'] if i['amount'] != '0.00') + '. Each needs a CA decision before anything is claimed.',
                'citations': [{'label': i['title'], 'ref': i['kind']} for i in s['items']]}
    if intent == 'suppliers':
        f = ctx.get('followups') or []
        if not f: return {'intent': intent, 'answer': 'No supplier follow-ups are needed for the latest reconciliation.', 'citations': []}
        return {'intent': intent, 'answer': f"Follow up with {len(f)} supplier(s): " + '; '.join(f"{d['supplier_name']} ({d['invoices']} invoice(s), ₹{d['credit_at_risk']} credit waiting)" for d in f) + '. Drafts are on the reconciliation screen.',
                'citations': [{'label': d['supplier_name'], 'ref': d['supplier_ref']} for d in f]}
    return {'intent': None, 'answer': "I can only answer questions about this period's own records. Try one of the suggested questions.", 'citations': [], 'suggestions': SUGGESTED}
