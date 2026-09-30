"""Purchase-only expense categories; no mutation of financial input or matching."""
import hashlib
import json
from datetime import date
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..dependencies import get_db, get_current_user, get_active_organization
from ...db.models import Client, GSTRegistration, FilingPeriod, ImportBatch, ImportRecord, CategoryProposal, CategoryDecision, CategoryRule, AuditEvent, User
from ...model_gateway.categorization import CATEGORIES, CategoryRequest, MockCategoryGateway, validated_suggestion

router = APIRouter(tags=['categories'])

def fingerprint(record):
    return hashlib.sha256(json.dumps(record.raw_data, sort_keys=True).encode()).hexdigest()

async def period_client(db, period_id, org_id):
    client = (await db.execute(select(Client).join(GSTRegistration).join(FilingPeriod).where(FilingPeriod.id == period_id, Client.organization_id == org_id))).scalars().first()
    if not client: raise HTTPException(404, 'Period not found')
    return client

async def eligible_record(db, record_id, org_id):
    row = (await db.execute(select(ImportRecord, ImportBatch).join(ImportBatch).join(FilingPeriod).join(GSTRegistration).join(Client).where(ImportRecord.id == record_id, Client.organization_id == org_id).with_for_update(of=ImportRecord))).first()
    if not row: raise HTTPException(404, 'Record not found')
    record, batch = row
    if batch.source_type != 'purchase' or batch.status != 'committed' or not record.is_valid:
        raise HTTPException(400, 'Only valid committed purchase records can be categorized')
    return record, batch

def proposal_view(p):
    return {'id':str(p.id), 'source':p.source, 'model_version':p.model_version, 'category':p.category, 'evidence':p.evidence, 'status':p.status, 'created_at':p.created_at.isoformat()}

def decision_view(d):
    return {'id':str(d.id), 'category':d.category, 'action':d.action, 'note':d.note, 'actor_id':str(d.user_id), 'created_at':d.created_at.isoformat()}

@router.get('/periods/{period_id}/categories')
async def list_categories(period_id: UUID, batch_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    client = await period_client(db, period_id, org_id)
    batch = await db.get(ImportBatch, batch_id)
    if not batch or batch.period_id != period_id or batch.source_type != 'purchase' or batch.status != 'committed':
        raise HTTPException(400, 'Select a committed purchase import for this period')
    records = (await db.execute(select(ImportRecord).where(ImportRecord.batch_id == batch_id, ImportRecord.is_valid.is_(True)).order_by(ImportRecord.row_number))).scalars().all()
    proposals = (await db.execute(select(CategoryProposal).join(ImportRecord).where(ImportRecord.batch_id == batch_id).order_by(CategoryProposal.created_at, CategoryProposal.id))).scalars().all()
    decisions = (await db.execute(select(CategoryDecision).join(ImportRecord).where(ImportRecord.batch_id == batch_id).order_by(CategoryDecision.created_at, CategoryDecision.id))).scalars().all()
    rules = (await db.execute(select(CategoryRule).where(CategoryRule.client_id == client.id).order_by(CategoryRule.created_at))).scalars().all()
    items = []
    for r in records[offset:offset+limit]:
        ds = [d for d in decisions if d.record_id == r.id]
        ps = [p for p in proposals if p.record_id == r.id]
        items.append({'id':str(r.id), 'record_id':r.raw_data.get('record_id'), 'supplier_ref':r.supplier_ref, 'description':r.raw_data.get('description',''), 'invoice_date':r.invoice_date, 'category':ds[-1].category if ds else None, 'last_decision_id':str(ds[-1].id) if ds else None, 'proposal':proposal_view(ps[-1]) if ps else None, 'history':[decision_view(d) for d in ds]})
    return {'categories':list(CATEGORIES), 'total':len(records), 'items':items, 'rules':[{'id':str(r.id),'supplier_ref':r.supplier_ref,'description':r.description,'category':r.category,'effective_from':r.effective_from,'active':r.active} for r in rules], 'mode':'mock-only'}

@router.post('/records/{record_id}/category-suggestion')
async def suggest(record_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    record, batch = await eligible_record(db, record_id, org_id)
    client = await period_client(db, batch.period_id, org_id)
    current = (await db.execute(select(CategoryProposal).where(CategoryProposal.record_id == record.id, CategoryProposal.status.in_(['proposed','needs_review'])).order_by(CategoryProposal.created_at.desc()))).scalars().first()
    description = record.raw_data.get('description','')
    rules = (await db.execute(select(CategoryRule).where(CategoryRule.client_id == client.id, CategoryRule.supplier_ref == record.supplier_ref, CategoryRule.description == description, CategoryRule.active.is_(True), CategoryRule.effective_from <= record.invoice_date))).scalars().all()
    if current and current.fingerprint == fingerprint(record):
        if (not rules and current.source == 'mock') or (len(rules) == 1 and current.source == 'approved_rule' and current.model_version == str(rules[0].id)):
            return proposal_view(current)
    if current: current.status = 'superseded'
    if len(rules) == 1:
        category, evidence, source, model_version = rules[0].category, description, 'approved_rule', str(rules[0].id)
    elif len(rules) > 1:
        category, evidence, source, model_version = None, None, 'rule_conflict', 'none'
    else:
        request = CategoryRequest(request_id=str(record.id), description=description, business_context=client.name, allowed_categories=list(CATEGORIES))
        response = validated_suggestion(MockCategoryGateway(), request)
        category, evidence, source, model_version = response.category, response.evidence_text, 'mock', response.model_version
    proposal = CategoryProposal(record_id=record.id, fingerprint=fingerprint(record), source=source, model_version=model_version, category=category, evidence=evidence, status='proposed' if category else 'needs_review')
    db.add(proposal); await db.commit(); await db.refresh(proposal)
    return proposal_view(proposal)

class DecisionInput(BaseModel):
    action: Literal['accept','reject','manual']
    category: str | None = None
    proposal_id: UUID | None = None
    previous_decision_id: UUID | None = None
    note: str = Field(min_length=1, max_length=2000)
    save_rule: bool = False
    effective_from: date | None = None

@router.post('/records/{record_id}/category-decisions')
async def decide(record_id: UUID, data: DecisionInput, user: User = Depends(get_current_user), org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    record, batch = await eligible_record(db, record_id, org_id)
    client = await period_client(db, batch.period_id, org_id)
    if not data.note.strip(): raise HTTPException(400, 'A review note is required')
    previous = (await db.execute(select(CategoryDecision).where(CategoryDecision.record_id == record.id).order_by(CategoryDecision.created_at.desc(), CategoryDecision.id.desc()))).scalars().first()
    if (previous.id if previous else None) != data.previous_decision_id: raise HTTPException(409, 'A newer decision exists. Reload before reviewing.')
    category = data.category
    proposal = None
    if data.action in ('accept','reject'):
        proposal = await db.get(CategoryProposal, data.proposal_id) if data.proposal_id else None
        if not proposal or proposal.record_id != record.id: raise HTTPException(404, 'Proposal not found')
        if proposal.status not in ('proposed','needs_review') or proposal.fingerprint != fingerprint(record): raise HTTPException(409, 'Proposal is stale or already reviewed')
        if data.action == 'accept':
            if proposal.source == 'approved_rule':
                rule = (await db.execute(select(CategoryRule).where(CategoryRule.id == UUID(proposal.model_version)).with_for_update())).scalars().first()
                if not rule or not rule.active: raise HTTPException(409, 'Mapping was deactivated. Request a new suggestion.')
            category = proposal.category
        else:
            category = previous.category if previous else None
    if data.action != 'reject' and category not in CATEGORIES: raise HTTPException(400, 'Choose a category from the allowed list')
    if data.save_rule:
        if data.action == 'reject' or not data.effective_from or not record.raw_data.get('description','').strip(): raise HTTPException(400, 'A mapping requires a category, description, and effective date')
        # Serialize rule creation per client to prevent concurrent conflicting mappings.
        await db.execute(select(Client).where(Client.id == client.id).with_for_update())
        existing = (await db.execute(select(CategoryRule).where(CategoryRule.client_id == client.id, CategoryRule.supplier_ref == record.supplier_ref, CategoryRule.description == record.raw_data['description'], CategoryRule.active.is_(True)))).scalars().first()
        if existing and (existing.category != category or existing.effective_from != data.effective_from.isoformat()): raise HTTPException(409, 'An active mapping already exists. Deactivate it before replacing it.')
        if not existing:
            db.add(CategoryRule(client_id=client.id, supplier_ref=record.supplier_ref, description=record.raw_data['description'], category=category, effective_from=data.effective_from.isoformat(), approved_by=user.id))
    if proposal: proposal.status = 'accepted' if data.action == 'accept' else 'rejected'
    # Any older unreviewed proposals become stale after a manual choice.
    if data.action == 'manual':
        pending = (await db.execute(select(CategoryProposal).where(CategoryProposal.record_id == record.id, CategoryProposal.status.in_(['proposed','needs_review'])))).scalars().all()
        for p in pending: p.status = 'superseded'
    event = CategoryDecision(record_id=record.id, proposal_id=proposal.id if proposal else None, user_id=user.id, action=data.action, category=category, note=data.note.strip())
    db.add(event); await db.flush()
    db.add(AuditEvent(organization_id=org_id,user_id=user.id,action='category_'+data.action,resource_type='category_decision',resource_id=str(event.id),period_id=batch.period_id,summary=category))
    await db.commit(); await db.refresh(event)
    return decision_view(event)

@router.post('/category-rules/{rule_id}/deactivate')
async def deactivate(rule_id: UUID, user: User = Depends(get_current_user), org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    rule = (await db.execute(select(CategoryRule).join(Client).where(CategoryRule.id == rule_id,Client.organization_id == org_id).with_for_update(of=CategoryRule))).scalars().first()
    if not rule: raise HTTPException(404,'Mapping not found')
    if rule.active:
        rule.active=False
        db.add(AuditEvent(organization_id=org_id,user_id=user.id,action='category_rule_deactivated',resource_type='category_rule',resource_id=str(rule.id)))
        await db.commit()
    return {'status':'inactive'}
