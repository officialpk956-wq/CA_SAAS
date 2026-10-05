"""Assistant endpoints: morning brief, savings finder, ITC suggestions, exception investigator, supplier
follow-ups, column mapping, ask-the-ledger and knowledge rules.

Read-only by design. The only writes are knowledge-rule records and applying a confirmed rule, both explicit
person-initiated actions that are audited. Suggestions are applied through the existing validated endpoints.
"""
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..dependencies import APPROVERS, get_db, get_active_organization, get_current_user, require_role
from .board import board_rows
from .sales import owned_period
from .worksheet import _draft_views, _gather, _itc_state, _owned_run, _ids, audit_events, reminder_state
from ... import assist, rules
from ...db.models import (Adjustment, AdjustmentVoid, AuditEvent, Client, FilingPeriod, GSTRegistration, ImportRecord, KnowledgeRule, LegalRule, Organization,
                          ReconciliationResult, ReconciliationRun, ResultDifference, RuleAcknowledgement, User)
from ...services.audit import record as audit
from ...services.ims import blocking as ims_blocking, ims_state
from ...services.cache import cached
from ...validation import parse_decimal

router = APIRouter(tags=['assist'])
SUPPLIER_FILE = Path(__file__).resolve().parents[4] / 'sample_data/v1/suppliers.csv'
MAX_MAPPING_BYTES = 5 * 1024 * 1024

def supplier_names():
    with open(SUPPLIER_FILE, encoding='utf-8-sig') as f:
        return {r['supplier_ref']: r['supplier_name'] for r in csv.DictReader(f)}

def _record(r: ImportRecord, side):
    base = {'record_id': r.record_id, 'side': side, 'row_number': r.row_number, 'supplier_ref': r.supplier_ref, 'document_type': r.document_type, 'invoice_number': r.invoice_number,
            'invoice_date': r.invoice_date, 'description': (r.raw_data or {}).get('description', '')}
    return base | {f: format(getattr(r, f), '.2f') for f in assist.AMOUNTS}

async def _run_context(db, run):
    """Valid records on both sides, results and latest ITC decision per result."""
    rows = lambda batch: db.execute(select(ImportRecord).where(ImportRecord.batch_id == batch, ImportRecord.is_valid.is_(True)))
    purchases = {r.record_id: _record(r, 'purchase') for r in (await rows(run.purchase_batch_id)).scalars().all()}
    statements = {r.record_id: _record(r, 'statement') for r in (await rows(run.statement_batch_id)).scalars().all()}
    results, history = await _itc_state(db, run)
    decision = {r.result_id: (history[r.result_id][-1].decision if history[r.result_id] else 'undecided') for r in results}
    return purchases, statements, results, decision

async def _latest_run(db, period_id):
    return (await db.execute(select(ReconciliationRun).where(ReconciliationRun.period_id == period_id, ReconciliationRun.status == 'succeeded')
                             .order_by(ReconciliationRun.created_at.desc()).limit(1))).scalars().first()

# --- Savings finder ---------------------------------------------------------------------------

def _reduces(p):
    """A credit note lowers credit, so it is never credit waiting, held back or left unclaimed."""
    return p.get('document_type') == 'credit_note'

async def active_legal(db, org_id):
    """CA-confirmed legal parameters by key. Missing keys mean the related check does not run."""
    rows = (await db.execute(select(LegalRule).where(LegalRule.organization_id == org_id, LegalRule.status == 'active'))).scalars().all()
    return {r.key: r.value | {'_source': r.source_reference} for r in rows}

def _legal_items(period, purchases, results, decision, drafts, legal, as_of):
    """Checks that need a confirmed legal rule. Each is skipped entirely if its rule is not confirmed."""
    items = []
    by_id = {r.result_id: r for r in results}
    if 'blocked_credit_keywords' in legal:
        words = legal['blocked_credit_keywords']['keywords']; hits = []
        for rid, d in decision.items():
            if d != 'claim': continue
            p = purchases[_ids(by_id[rid].purchase_record_ids)[0]]
            word = rules.blocked_keyword(p['description'], words)
            if word and not _reduces(p): hits.append((p, word))
        if hits:
            items.append({'kind': 'possibly_blocked_credit', 'title': 'Claimed credit may be blocked', 'amount': format(sum((assist.tax_of(p) for p, _ in hits), Decimal('0.00')), '.2f'),
                          'detail': '; '.join(f"{p['record_id']} “{p['description']}” matches “{w}”" for p, w in hits), 'needs_ca': True,
                          'action': f"Review before approval (rule source: {legal['blocked_credit_keywords']['_source']}).", 'evidence': [p['record_id'] for p, _ in hits]})
    if 'itc_claim_deadline' in legal:
        rule = legal['itc_claim_deadline']; near = []
        for rid, d in decision.items():
            r = by_id[rid]
            unclaimed = (r.status == 'books_only' and d != 'claim') or (r.status == 'matched' and d in ('not_claimed', 'deferred', 'undecided'))
            if not unclaimed: continue
            p = purchases[_ids(r.purchase_record_ids)[0]]
            if _reduces(p): continue
            deadline = rules.claim_deadline(date.fromisoformat(p['invoice_date']), rule['day'], rule['month'])
            if (deadline - as_of).days <= rule['warn_days']: near.append((p, deadline))
        if near:
            first = min(d for _, d in near)
            items.append({'kind': 'claim_deadline', 'title': 'Unclaimed credit near its claim deadline' if first >= as_of else 'Claim deadline has passed for some credit',
                          'amount': format(sum((assist.tax_of(p) for p, _ in near), Decimal('0.00')), '.2f'),
                          'detail': f"{len(near)} invoice(s); earliest deadline {first.isoformat()} ({(first - as_of).days} day(s) from {as_of.isoformat()}).", 'needs_ca': True,
                          'action': f"Resolve or claim before the deadline (rule source: {rule['_source']}).", 'evidence': [p['record_id'] for p, _ in near]})
    latest = drafts[0] if drafts else None
    filed = any(d['approval'] and not d['approval']['reopen'] and d['approval']['filing_evidence'] for d in drafts)
    if latest and latest['payload'].get('worksheet') and not filed:
        positive = sum((max(Decimal(v['net']), Decimal('0')) for v in latest['payload']['worksheet']['heads'].values()), Decimal('0.00'))
        if 'late_payment_interest' in legal and positive > 0:
            rule = legal['late_payment_interest']; days = (as_of - rules.due_date(period.period_code, rule['due_day'])).days
            est = rules.interest_estimate(positive, Decimal(rule['rate_percent']), days)
            if est > 0:
                items.append({'kind': 'interest_estimate', 'title': 'Interest building up (estimate)', 'amount': format(est, '.2f'), 'needs_ca': True,
                              'detail': f"{days} day(s) past the due date on a positive net of ₹{assist.fmt(positive)} at {rule['rate_percent']}% a year. Rough: ignores credit ledgers and set-off.",
                              'action': f"Prioritise approval and payment (rule source: {rule['_source']}).", 'evidence': []})
        if 'late_fee' in legal:
            rule = legal['late_fee']; days = (as_of - rules.due_date(period.period_code, rule['due_day'])).days
            fee = rules.late_fee_estimate(days, Decimal(rule['per_day']), Decimal(rule['cap']))
            if fee > 0:
                items.append({'kind': 'late_fee_estimate', 'title': 'Late fee building up (estimate)', 'amount': format(fee, '.2f'), 'needs_ca': True,
                              'detail': f"{days} day(s) past the return due date; no filing reference recorded.", 'action': f"File and record the reference (rule source: {rule['_source']}).", 'evidence': []})
    return items

async def _period_savings(db, period, org_id, as_of: date, legal=None):
    """Credit at risk or left unclaimed, computed from recorded rows only. Every item needs a CA decision."""
    items = []; money = assist.money
    legal = await active_legal(db, org_id) if legal is None else legal
    run = await _latest_run(db, period.id)
    drafts = await _draft_views(db, period, org_id) if {'late_payment_interest', 'late_fee'} & set(legal) else []
    if not run and drafts: items += _legal_items(period, {}, [], {}, drafts, legal, as_of)
    if run:
        purchases, statements, results, decision = await _run_context(db, run)
        items += _legal_items(period, purchases, results, decision, drafts, legal, as_of)
        by_status = defaultdict(list)
        for r in results: by_status[r.status].append(r)
        waiting = defaultdict(lambda: Decimal('0.00')); refs = defaultdict(list)
        for r in by_status['books_only']:
            if decision[r.result_id] == 'claim': continue
            p = purchases[_ids(r.purchase_record_ids)[0]]
            if _reduces(p): continue
            waiting[p['supplier_ref']] += assist.tax_of(p); refs[p['supplier_ref']].append(p['record_id'])
        if waiting:
            items.append({'kind': 'waiting_on_supplier', 'title': 'Credit waiting on suppliers', 'amount': format(sum(waiting.values()), '.2f'),
                          'detail': '; '.join(f'{s}: ₹{assist.fmt(v)} ({", ".join(refs[s])})' for s, v in waiting.items()),
                          'action': 'Send the supplier follow-ups and re-check in the next statement before the claim window closes.', 'needs_ca': False,
                          'evidence': [x for v in refs.values() for x in v]})
        more = Decimal('0.00'); ev = []
        for r in by_status['amount_mismatch']:
            p = purchases[_ids(r.purchase_record_ids)[0]]; s = statements[_ids(r.statement_record_ids)[0]]
            gap = assist.tax_of(s) - assist.tax_of(p)
            if gap > 0 and not _reduces(p): more += gap; ev.append(p['record_id'])
        if more:
            items.append({'kind': 'statement_shows_more_tax', 'title': 'Statement shows more tax than your books', 'amount': format(more, '.2f'),
                          'detail': f'{len(ev)} mismatched invoice(s): {", ".join(ev)}', 'action': 'Check the invoice copies; if the statement is right, correct the books in a new import version.', 'needs_ca': False, 'evidence': ev})
        held = [r for r in by_status['matched'] if decision[r.result_id] in ('not_claimed', 'deferred') and not _reduces(purchases[_ids(r.purchase_record_ids)[0]])]
        if held:
            total = sum((assist.tax_of(purchases[_ids(r.purchase_record_ids)[0]]) for r in held), Decimal('0.00'))
            items.append({'kind': 'matched_not_claimed', 'title': 'Exact matches not claimed', 'amount': format(total, '.2f'),
                          'detail': f'{len(held)} exact match(es) marked not claimed or deferred.', 'action': 'Review whether the reason still holds.', 'needs_ca': True, 'evidence': [r.result_id for r in held]})
        dups = len(by_status['duplicate_candidate'])
        if dups:
            items.append({'kind': 'duplicates', 'title': 'Duplicate entries to resolve', 'amount': '0.00', 'detail': f'{dups} duplicate group(s) — resolving them protects against over-claiming.',
                          'action': 'Correct the duplicate book entries.', 'needs_ca': False, 'evidence': [r.result_id for r in by_status['duplicate_candidate']]})
    adjustments = (await db.execute(select(Adjustment).where(Adjustment.period_id == period.id))).scalars().all()
    voided = {v.adjustment_id for v in (await db.execute(select(AdjustmentVoid).join(Adjustment).where(Adjustment.period_id == period.id))).scalars().all()}
    rcm = defaultdict(lambda: Decimal('0.00')); credit = defaultdict(lambda: Decimal('0.00'))
    for a in adjustments:
        if a.id in voided: continue
        if a.adjustment_type == 'rcm_liability': rcm[a.tax_head] += a.amount
        if a.adjustment_type == 'other_credit': credit[a.tax_head] += a.amount
    gap = {h: rcm[h] - credit[h] for h in rcm if rcm[h] > credit[h]}
    if gap:
        items.append({'kind': 'rcm_without_credit', 'title': 'Reverse-charge paid, no matching credit recorded', 'amount': format(sum(gap.values()), '.2f'),
                      'detail': '; '.join(f'{h.upper()} ₹{assist.fmt(v)}' for h, v in gap.items()), 'action': 'Ask the CA whether credit is available for this reverse-charge tax.', 'needs_ca': True, 'evidence': []})
    total = sum((money(i['amount']) for i in items), Decimal('0.00'))
    return {'period_id': str(period.id), 'period_code': period.period_code, 'total': format(total, '.2f'), 'items': items,
            'notice': 'Opportunities computed from recorded rows. Each is a question for the CA; nothing is claimed automatically.'}

async def _repeat_suppliers(db, client_id):
    """Suppliers with invoices missing from statements in two or more periods of the same client."""
    periods = (await db.execute(select(FilingPeriod).join(GSTRegistration).where(GSTRegistration.client_id == client_id))).scalars().all()
    seen = defaultdict(set)
    for p in periods:
        run = await _latest_run(db, p.id)
        if not run: continue
        purchases, _, results, _ = await _run_context(db, run)
        for r in results:
            if r.status == 'books_only': seen[purchases[_ids(r.purchase_record_ids)[0]]['supplier_ref']].add(p.period_code)
    return {s: sorted(v) for s, v in seen.items() if len(v) >= 2}

@router.get('/periods/{period_id}/savings')
async def period_savings(period_id: UUID, as_of: date | None = None, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    period = await owned_period(db, period_id, org_id)
    out = await _period_savings(db, period, org_id, as_of or date.today())
    client_id = (await db.execute(select(GSTRegistration.client_id).where(GSTRegistration.id == period.registration_id))).scalar_one()
    repeat = await _repeat_suppliers(db, client_id)
    if repeat:
        out['items'].append({'kind': 'repeat_suppliers', 'title': 'Suppliers who repeatedly miss filing', 'amount': '0.00',
                             'detail': '; '.join(f'{s}: {", ".join(v)}' for s, v in repeat.items()), 'action': 'Raise it with the supplier; consider holding the tax portion of payment until they file.', 'needs_ca': False, 'evidence': list(repeat)})
    return out

async def _org_savings(db, org_id, as_of: date):
    return await cached(db, org_id, 'savings', lambda: _compute_org_savings(db, org_id, as_of), as_of.isoformat())

async def _compute_org_savings(db, org_id, as_of):
    periods = (await db.execute(select(FilingPeriod, Client.name).select_from(FilingPeriod).join(GSTRegistration, FilingPeriod.registration_id == GSTRegistration.id).join(Client, GSTRegistration.client_id == Client.id).where(Client.organization_id == org_id))).all()
    rows = []; legal = await active_legal(db, org_id)
    for period, name in periods:
        s = await _period_savings(db, period, org_id, as_of, legal)
        if s['items']: rows.append({'period_id': s['period_id'], 'period_code': s['period_code'], 'client_name': name, 'total': s['total'], 'items': len(s['items'])})
    total = sum((assist.money(r['total']) for r in rows), Decimal('0.00'))
    return {'total': format(total, '.2f'), 'periods': sorted(rows, key=lambda r: assist.money(r['total']), reverse=True)}

@router.get('/savings')
async def org_savings(as_of: date | None = None, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    return await _org_savings(db, org_id, as_of or date.today())

# --- Morning brief ----------------------------------------------------------------------------

@router.get('/brief')
async def brief(org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    async def compute():
        rows = await cached(db, org_id, 'board', lambda: board_rows(db, org_id))
        events = (await db.execute(select(AuditEvent.action).where(AuditEvent.organization_id == org_id, AuditEvent.created_at >= now - timedelta(hours=24)))).scalars().all()
        savings = await _org_savings(db, org_id, now.date())
        return {'generated_at': now.isoformat(), 'items': assist.morning_brief(rows, [{'action': a} for a in events], assist.money(savings['total'])),
                'source': 'Built from the Board and the audit trail; no model involved.'}
    # The "last 24 hours" sentence depends on the clock, so cached briefs are also keyed by the hour.
    return await cached(db, org_id, 'brief', compute, now.strftime('%Y-%m-%dT%H'))

# --- ITC suggestions, investigator, follow-ups ------------------------------------------------

@router.get('/runs/{run_id}/itc-suggestions')
async def itc_suggestions(run_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    run = await _owned_run(db, run_id, org_id)
    results, history = await _itc_state(db, run)
    purchases = (await _run_context(db, run))[0] if run.status == 'succeeded' else {}
    kind = lambda r: purchases.get(next(iter(_ids(r.purchase_record_ids)), None), {}).get('document_type', 'invoice')
    rows = [{'result_id': r.result_id, 'status': r.status, 'document_type': kind(r), 'decision': history[r.result_id][-1].decision if history[r.result_id] else 'undecided'} for r in results]
    suggestions = assist.itc_suggestions(rows)
    legal = await active_legal(db, org_id)
    if 'blocked_credit_keywords' in legal and run.status == 'succeeded':
        by_id = {r.result_id: r for r in results}
        for s in suggestions:
            if s['decision'] != 'claim': continue
            word = rules.blocked_keyword(purchases[_ids(by_id[s['result_id']].purchase_record_ids)[0]]['description'], legal['blocked_credit_keywords']['keywords'])
            if word: s.update(decision='deferred', reason=f'Description matches the firm’s confirmed blocked-credit word “{word}”; CA to confirm before claiming.')
    ims = await ims_state(db, run.statement_batch_id)
    if ims:
        by_id = {r.result_id: r for r in results}
        for s in suggestions:
            if s['decision'] != 'claim': continue
            why = ims_blocking(ims, _ids(by_id[s['result_id']].statement_record_ids))
            if why: s.update(decision='not_claimed' if 'rejected' in why else 'deferred', reason=f'{why[0].upper()}{why[1:]}; cannot be claimed this period.')
    counts = defaultdict(int)
    for s in suggestions: counts[s['decision']] += 1
    return {'suggestions': suggestions, 'counts': dict(counts), 'note': 'Suggestions only. Accepting sends them through the normal ITC decision checks.'}

@router.get('/runs/{run_id}/results/{result_id}/investigate')
async def investigate(run_id: UUID, result_id: str, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    run = await _owned_run(db, run_id, org_id)
    if run.status != 'succeeded': raise HTTPException(400, 'Investigation needs a succeeded run')
    purchases, statements, results, _ = await _run_context(db, run)
    result = next((r for r in results if r.result_id == result_id), None)
    if not result: raise HTTPException(404, 'Result not found')
    pids, sids = _ids(result.purchase_record_ids), _ids(result.statement_record_ids)
    own = [purchases[i] for i in pids if i in purchases] + [statements[i] for i in sids if i in statements]
    unmatched = {'books_only': [], 'statement_only': []}
    for r in results:
        if r.status == 'books_only': unmatched['books_only'] += [purchases[i] for i in _ids(r.purchase_record_ids) if i in purchases]
        if r.status == 'statement_only': unmatched['statement_only'] += [statements[i] for i in _ids(r.statement_record_ids) if i in statements]
    other = unmatched['statement_only'] if result.status == 'books_only' else unmatched['books_only'] if result.status == 'statement_only' else []
    diffs = {d.field_name: format(d.difference_value, '.2f') for d in (await db.execute(select(ResultDifference).join(ReconciliationResult).where(ReconciliationResult.run_id == run.id, ReconciliationResult.result_id == result_id))).scalars().all()}
    out = assist.investigate({'status': result.status, 'differences': diffs}, own, other)
    return out | {'result_id': result_id, 'status': result.status, 'records': own, 'source': 'Deterministic search within this run; the engine result is unchanged.'}

@router.get('/runs/{run_id}/supplier-followups')
async def supplier_followups(run_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    run = await _owned_run(db, run_id, org_id)
    if run.status != 'succeeded': raise HTTPException(400, 'Follow-ups need a succeeded run')
    purchases, statements, results, _ = await _run_context(db, run)
    period, client_name = (await db.execute(select(FilingPeriod, Client.name).select_from(FilingPeriod).join(GSTRegistration, FilingPeriod.registration_id == GSTRegistration.id).join(Client, GSTRegistration.client_id == Client.id).where(FilingPeriod.id == run.period_id))).first()
    items = []
    for r in results:
        if r.status == 'books_only':
            p = purchases[_ids(r.purchase_record_ids)[0]]; items.append({'supplier_ref': p['supplier_ref'], 'kind': 'missing', 'record': p, 'differences': {}})
        elif r.status == 'amount_mismatch':
            p = purchases[_ids(r.purchase_record_ids)[0]]; s = statements[_ids(r.statement_record_ids)[0]]
            items.append({'supplier_ref': p['supplier_ref'], 'kind': 'mismatch', 'record': p, 'differences': {f: format(assist.money(p[f]) - assist.money(s[f]), '.2f') for f in assist.AMOUNTS if p[f] != s[f]}})
    return {'drafts': assist.supplier_followups(items, supplier_names(), client_name, period.period_code), 'note': 'Drafts only. Copy and send them yourself; GST Helper sends nothing.'}

# --- Column mapper ----------------------------------------------------------------------------

Template = Literal['purchase', 'statement', 'sales']

async def _read_upload(file: UploadFile):
    content = await file.read(MAX_MAPPING_BYTES + 1)
    if len(content) > MAX_MAPPING_BYTES: raise HTTPException(413, 'File exceeds 5 MiB')
    try: content.decode('utf-8-sig')
    except UnicodeDecodeError: raise HTTPException(400, 'File must be UTF-8 CSV')
    return content

@router.post('/column-mapping/propose')
async def propose_mapping(template: Template = Form(...), file: UploadFile = File(...), org_id: UUID = Depends(get_active_organization)):
    headers = assist.read_headers(await _read_upload(file))
    if not headers: raise HTTPException(400, 'The file has no header row')
    return assist.propose_mapping(headers, template) | {'source_headers': headers, 'fields': assist.TEMPLATES[template], 'optional': sorted(assist.OPTIONAL)}

@router.post('/column-mapping/apply')
async def apply_mapping(template: Template = Form(...), mapping: str = Form(...), file: UploadFile = File(...), org_id: UUID = Depends(get_active_organization)):
    try: chosen = json.loads(mapping)
    except json.JSONDecodeError: raise HTTPException(400, 'Mapping must be JSON')
    if not isinstance(chosen, dict): raise HTTPException(400, 'Mapping must be an object of template field to source column')
    try: converted = assist.apply_mapping(await _read_upload(file), template, chosen)
    except ValueError as exc: raise HTTPException(400, str(exc))
    name = (file.filename or 'mapped.csv').rsplit('.', 1)[0][:150] + '_mapped.csv'
    return Response(converted, media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="{name}"'})

# --- Ask the ledger ---------------------------------------------------------------------------

class AskInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=1, max_length=500)
    sales_batch_id: UUID | None = None
    run_id: UUID | None = None

@router.post('/periods/{period_id}/ask')
async def ask(period_id: UUID, data: AskInput, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    period = await owned_period(db, period_id, org_id)
    drafts = await _draft_views(db, period, org_id)
    blockers = None
    if data.sales_batch_id and data.run_id:
        _, blockers, _ = await _gather(db, period, data.sales_batch_id, data.run_id, org_id)
    events = await audit_events(period_id=period.id, offset=0, limit=200, org_id=org_id, db=db)
    run = await _latest_run(db, period.id)
    followups = (await supplier_followups(run.id, org_id=org_id, db=db))['drafts'] if run else []
    ctx = {'period_code': period.period_code, 'draft': drafts[0] if drafts else None, 'blockers': blockers, 'events': events,
           'savings': await _period_savings(db, period, org_id, date.today()), 'followups': followups}
    return assist.ask(data.question, ctx) | {'source': "Answered from this period's records only; no model involved."}

# --- Knowledge rules --------------------------------------------------------------------------

def _rule_view(r: KnowledgeRule, client_name=None):
    return {'id': str(r.id), 'client_id': str(r.client_id) if r.client_id else None, 'client_name': client_name if r.client_id else 'All clients (firm-wide)',
            'note': r.note, 'rule_kind': r.rule_kind, 'frequency': r.frequency, 'adjustment_type': r.adjustment_type, 'tax_head': r.tax_head,
            'amount': format(r.amount, '.2f') if r.amount is not None else None, 'effective_from': r.effective_from, 'effective_to': r.effective_to,
            'status': r.status, 'created_at': r.created_at.isoformat(), 'decided_at': r.decided_at.isoformat() if r.decided_at else None}

def _rules_query(org_id):
    return (select(KnowledgeRule, Client.name).select_from(KnowledgeRule).outerjoin(Client, KnowledgeRule.client_id == Client.id)
            .where(KnowledgeRule.organization_id == org_id))

async def _owned_client(db, client_id, org_id):
    client = (await db.execute(select(Client).where(Client.id == client_id, Client.organization_id == org_id))).scalars().first()
    if not client: raise HTTPException(404, 'Client not found')
    return client

async def _owned_rule(db, rule_id, org_id, lock=False):
    q = _rules_query(org_id).where(KnowledgeRule.id == rule_id)
    if lock: q = q.with_for_update(of=KnowledgeRule)
    row = (await db.execute(q)).first()
    if not row: raise HTTPException(404, 'Rule not found')
    return row

@router.get('/knowledge-rules')
async def list_rules(org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(_rules_query(org_id).order_by(KnowledgeRule.created_at.desc()))).all()
    return [_rule_view(r, name) for r, name in rows]

class DraftInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    note: str = Field(min_length=3, max_length=2000)
    client_id: UUID | None = None  # None = firm-wide (reminders only)

@router.post('/knowledge-rules/draft')
async def draft_rule(data: DraftInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    client = await _owned_client(db, data.client_id, org_id) if data.client_id else None
    parsed = assist.parse_rule_note(data.note)
    rule = KnowledgeRule(organization_id=org_id, client_id=client.id if client else None, note=data.note.strip(), rule_kind=parsed['rule_kind'], frequency=parsed['frequency'],
                         adjustment_type=parsed['adjustment_type'], tax_head=parsed['tax_head'], amount=Decimal(parsed['amount']) if parsed['amount'] else None,
                         effective_from=parsed['effective_from'], effective_to=parsed['effective_to'], status='proposed', created_by=user.id)
    db.add(rule); await db.flush()
    audit(db, org_id, user.id, 'rule_proposed', 'knowledge_rule', rule.id, None, f"{client.name if client else 'Firm-wide'}: {data.note.strip()[:120]}")
    await db.commit(); await db.refresh(rule)
    return _rule_view(rule, client.name if client else None) | {'missing': parsed['missing']}

MONTH = r'^\d{4}-(0[1-9]|1[0-2])$'

class ConfirmInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rule_kind: Literal['adjustment', 'reminder'] = 'adjustment'
    frequency: Literal['monthly', 'quarterly', 'one_time'] = 'monthly'
    adjustment_type: Literal['rcm_liability', 'other_liability', 'itc_reversal', 'other_credit'] | None = None
    tax_head: Literal['igst', 'cgst', 'sgst', 'cess'] | None = None
    amount: str | None = None
    effective_from: str = Field(pattern=MONTH)
    effective_to: str | None = Field(default=None, pattern=MONTH)

@router.post('/knowledge-rules/{rule_id}/confirm')
async def confirm_rule(rule_id: UUID, data: ConfirmInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rule, name = await _owned_rule(db, rule_id, org_id, lock=True)
    if rule.status != 'proposed': raise HTTPException(409, f'Rule is already {rule.status}')
    if data.effective_to and data.effective_to < data.effective_from: raise HTTPException(400, 'The end month is before the start month')
    if data.rule_kind == 'adjustment':
        if not rule.client_id: raise HTTPException(400, 'Adjustment rules belong to one client; firm-wide rules can only be reminders')
        if not (data.adjustment_type and data.tax_head and data.amount): raise HTTPException(400, 'Adjustment rules need a type, tax head and amount')
        try: amount = parse_decimal(data.amount)
        except ValueError: raise HTTPException(400, 'Amount must be a nonnegative decimal with exactly two places')
        rule.adjustment_type, rule.tax_head, rule.amount = data.adjustment_type, data.tax_head, amount
    else:
        rule.adjustment_type = rule.tax_head = rule.amount = None
    rule.rule_kind, rule.frequency, rule.effective_from, rule.effective_to = data.rule_kind, data.frequency, data.effective_from, data.effective_to
    rule.status, rule.decided_by, rule.decided_at = 'active', user.id, datetime.now(timezone.utc)
    what = f'{rule.adjustment_type} {rule.tax_head} {format(rule.amount, ".2f")}' if data.rule_kind == 'adjustment' else 'reminder'
    audit(db, org_id, user.id, 'rule_confirmed', 'knowledge_rule', rule.id, None, f"{name or 'Firm-wide'}: {what} {data.frequency} from {data.effective_from}{' to ' + data.effective_to if data.effective_to else ''}")
    await db.commit(); await db.refresh(rule)
    return _rule_view(rule, name)

@router.post('/knowledge-rules/{rule_id}/dismiss')
async def dismiss_rule(rule_id: UUID, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _close_rule(db, rule_id, 'dismiss', org_id, user)

@router.post('/knowledge-rules/{rule_id}/retire')
async def retire_rule(rule_id: UUID, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _close_rule(db, rule_id, 'retire', org_id, user)

async def _close_rule(db, rule_id, action, org_id, user):
    rule, name = await _owned_rule(db, rule_id, org_id, lock=True)
    allowed = {'dismiss': 'proposed', 'retire': 'active'}[action]
    if rule.status != allowed: raise HTTPException(409, f'Only {allowed} rules can be {action}ed')
    rule.status, rule.decided_by, rule.decided_at = {'dismiss': 'dismissed', 'retire': 'retired'}[action], user.id, datetime.now(timezone.utc)
    audit(db, org_id, user.id, f'rule_{rule.status}', 'knowledge_rule', rule.id, None, f"{name or 'Firm-wide'}: {rule.note[:120]}")
    await db.commit(); await db.refresh(rule)
    return _rule_view(rule, name)

async def _active_rule_adjustments(db, period_id):
    adjustments = (await db.execute(select(Adjustment).where(Adjustment.period_id == period_id, Adjustment.rule_id.is_not(None)))).scalars().all()
    voided = {v.adjustment_id for v in (await db.execute(select(AdjustmentVoid).join(Adjustment).where(Adjustment.period_id == period_id))).scalars().all()}
    return {a.rule_id for a in adjustments if a.id not in voided}

async def _period_client(db, period):
    return (await db.execute(select(GSTRegistration.client_id).where(GSTRegistration.id == period.registration_id))).scalar_one()

@router.get('/periods/{period_id}/applicable-rules')
async def applicable_rules(period_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    """Active rules that apply to this period: client-specific adjustments, and client or firm-wide reminders."""
    period = await owned_period(db, period_id, org_id)
    client_id = await _period_client(db, period)
    candidates = (await db.execute(select(KnowledgeRule).where(KnowledgeRule.organization_id == org_id, KnowledgeRule.status == 'active',
                                                            or_(KnowledgeRule.client_id == client_id, KnowledgeRule.client_id.is_(None))))).scalars().all()
    applied = await _active_rule_adjustments(db, period.id)
    acks = {a.rule_id: a for a in (await db.execute(select(RuleAcknowledgement).where(RuleAcknowledgement.period_id == period.id))).scalars().all()}
    out = []
    for r in candidates:
        if not rules.rule_applies(r.frequency, r.effective_from, r.effective_to, period.period_code): continue
        view = _rule_view(r) | {'applied': r.id in applied}
        if r.rule_kind == 'reminder':
            ack = acks.get(r.id)
            view['acknowledged'] = {'note': ack.note, 'created_at': ack.created_at.isoformat()} if ack else None
        out.append(view)
    return out

class ApplyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    period_id: UUID

@router.post('/knowledge-rules/{rule_id}/apply')
async def apply_rule(rule_id: UUID, data: ApplyInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    period = await owned_period(db, data.period_id, org_id, lock=True)
    rule, name = await _owned_rule(db, rule_id, org_id)
    if rule.rule_kind != 'adjustment': raise HTTPException(400, 'Reminders are acknowledged, not applied')
    if rule.client_id != await _period_client(db, period): raise HTTPException(400, 'This rule belongs to another client')
    if rule.status != 'active': raise HTTPException(409, 'Only active rules can be applied')
    if not rules.rule_applies(rule.frequency, rule.effective_from, rule.effective_to, period.period_code):
        raise HTTPException(400, f'This {rule.frequency.replace("_", "-")} rule does not apply to {period.period_code}')
    if rule.id in await _active_rule_adjustments(db, period.id): raise HTTPException(409, 'This rule is already applied to the period')
    adj = Adjustment(period_id=period.id, user_id=user.id, adjustment_type=rule.adjustment_type, tax_head=rule.tax_head, amount=rule.amount, note=f'Rule: {rule.note[:1900]}', rule_id=rule.id)
    db.add(adj); await db.flush()
    audit(db, org_id, user.id, 'rule_applied', 'tax_adjustment', adj.id, period.id, f'{rule.adjustment_type} {rule.tax_head} {format(rule.amount, ".2f")} from rule')
    await db.commit()
    return {'adjustment_id': str(adj.id), 'rule_id': str(rule.id)}

class AckInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    period_id: UUID
    note: str = Field(min_length=1, max_length=2000)

@router.post('/knowledge-rules/{rule_id}/acknowledge')
async def acknowledge_rule(rule_id: UUID, data: AckInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    period = await owned_period(db, data.period_id, org_id, lock=True)
    rule, name = await _owned_rule(db, rule_id, org_id)
    if rule.rule_kind != 'reminder' or rule.status != 'active': raise HTTPException(400, 'Only active reminders can be acknowledged')
    if not data.note.strip(): raise HTTPException(400, 'Say what was checked')
    reminders, acks = await reminder_state(db, period, org_id)
    if rule.id not in {r.id for r in reminders}: raise HTTPException(400, 'This reminder does not apply to the period')
    if rule.id in acks: raise HTTPException(409, 'Already acknowledged for this period')
    ack = RuleAcknowledgement(rule_id=rule.id, period_id=period.id, user_id=user.id, note=data.note.strip())
    db.add(ack); await db.flush()
    audit(db, org_id, user.id, 'reminder_acknowledged', 'knowledge_rule', rule.id, period.id, f'{rule.note[:80]} — {data.note.strip()[:80]}')
    await db.commit()
    return {'id': str(ack.id), 'rule_id': str(rule.id)}

# --- Legal rule register (CA-confirmed statutory parameters) --------------------------------

def _legal_view(r: LegalRule):
    return {'id': str(r.id), 'key': r.key, 'value': r.value, 'source_reference': r.source_reference, 'effective_from': r.effective_from, 'status': r.status,
            'confirmed_by': str(r.confirmed_by), 'confirmed_at': r.confirmed_at.isoformat()}

@router.get('/legal-rules')
async def legal_rules(org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(LegalRule).where(LegalRule.organization_id == org_id).order_by(LegalRule.confirmed_at.desc()))).scalars().all()
    out = []
    for key, t in rules.LEGAL_TEMPLATES.items():
        versions = [_legal_view(r) for r in rows if r.key == key]
        out.append({'key': key, 'title': t['title'], 'help': t['help'], 'fields': t['fields'], 'options': t.get('options', {}),
                    'active': next((v for v in versions if v['status'] == 'active'), None), 'history': versions})
    return {'rules': out, 'notice': 'Values are entered and confirmed by the firm. GST Helper ships none; a check runs only once its rule is confirmed.'}

class LegalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: dict
    source_reference: str = Field(min_length=3, max_length=500)
    effective_from: str = Field(pattern=MONTH)
    checked_against_current_law: bool

@router.post('/legal-rules/{key}/confirm')
async def confirm_legal(key: str, data: LegalInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(user, *APPROVERS)  # statutory values are confirmed by an owner or reviewer, not a preparer
    if key not in rules.LEGAL_TEMPLATES: raise HTTPException(404, 'Unknown legal rule')
    if not data.checked_against_current_law: raise HTTPException(400, 'Confirm that you checked the value against current law')
    if not data.source_reference.strip(): raise HTTPException(400, 'A source reference is required')
    try: value = rules.validate_legal_value(key, data.value)
    except ValueError as exc: raise HTTPException(400, str(exc))
    await db.execute(select(Organization).where(Organization.id == org_id).with_for_update())  # one active version per key, even under concurrent confirmations
    current = (await db.execute(select(LegalRule).where(LegalRule.organization_id == org_id, LegalRule.key == key, LegalRule.status == 'active').with_for_update())).scalars().all()
    for r in current: r.status = 'retired'
    rule = LegalRule(organization_id=org_id, key=key, value=value, source_reference=data.source_reference.strip(), effective_from=data.effective_from, status='active', confirmed_by=user.id)
    db.add(rule); await db.flush()
    audit(db, org_id, user.id, 'legal_rule_confirmed', 'legal_rule', rule.id, None, f"{rules.LEGAL_TEMPLATES[key]['title']}: {json.dumps(value)} (source: {data.source_reference.strip()[:120]})")
    await db.commit(); await db.refresh(rule)
    return _legal_view(rule)

@router.post('/legal-rules/{key}/retire')
async def retire_legal(key: str, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    current = (await db.execute(select(LegalRule).where(LegalRule.organization_id == org_id, LegalRule.key == key, LegalRule.status == 'active').with_for_update())).scalars().all()
    if not current: raise HTTPException(404, 'No active rule to retire')
    require_role(user, *APPROVERS)
    for r in current: r.status = 'retired'
    audit(db, org_id, user.id, 'legal_rule_retired', 'legal_rule', current[0].id, None, rules.LEGAL_TEMPLATES.get(key, {}).get('title', key))
    await db.commit()
    return {'status': 'retired'}
