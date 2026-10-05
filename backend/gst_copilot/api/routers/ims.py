"""IMS inbox: accept, reject or keep pending each supplier invoice of a committed statement import.

Actions are append-only (latest applies) and audited. Rejected or pending invoices cannot be claimed as ITC
(see services/ims.py for the workflow mapping, pending CA review).
"""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..dependencies import get_db, get_active_organization, get_current_user
from ...db.models import Client, FilingPeriod, GSTRegistration, ImportBatch, ImportRecord, ImsAction, ReconciliationResult, ReconciliationRun, User
from ...services.audit import record as audit
from ...services.ims import ims_state

router = APIRouter(tags=['ims'])

async def _statement_batch(db, batch_id, org_id, lock=False):
    q = select(ImportBatch).join(FilingPeriod).join(GSTRegistration).join(Client).where(ImportBatch.id == batch_id, Client.organization_id == org_id)
    if lock: q = q.with_for_update(of=ImportBatch)
    batch = (await db.execute(q)).scalars().first()
    if not batch: raise HTTPException(404, 'Import not found')
    if batch.source_type != 'statement': raise HTTPException(400, 'IMS actions apply to supplier statement imports only')
    if batch.status != 'committed': raise HTTPException(400, 'Commit the statement import before taking IMS actions')
    return batch

def _ids(v): return v.get('ids', []) if isinstance(v, dict) else v

@router.get('/imports/{batch_id}/ims')
async def ims_inbox(batch_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    batch = await _statement_batch(db, batch_id, org_id)
    records = (await db.execute(select(ImportRecord).where(ImportRecord.batch_id == batch.id, ImportRecord.is_valid.is_(True)).order_by(ImportRecord.row_number))).scalars().all()
    history = await ims_state(db, batch.id)
    # Reconciliation finding for each invoice, from the latest succeeded run that used this statement.
    run = (await db.execute(select(ReconciliationRun).where(ReconciliationRun.statement_batch_id == batch.id, ReconciliationRun.status == 'succeeded').order_by(ReconciliationRun.created_at.desc()).limit(1))).scalars().first()
    finding = {}
    if run:
        for r in (await db.execute(select(ReconciliationResult).where(ReconciliationResult.run_id == run.id))).scalars().all():
            for sid in _ids(r.statement_record_ids): finding[sid] = r.status
    items = []
    for rec in records:
        h = history.get(rec.record_id, [])
        items.append({'id': str(rec.id), 'record_id': rec.record_id, 'supplier_ref': rec.supplier_ref, 'invoice_number': rec.invoice_number, 'invoice_date': rec.invoice_date,
                      'taxable_value': format(rec.taxable_value, '.2f'), 'tax': format(rec.cgst + rec.sgst + rec.igst + rec.cess, '.2f'), 'finding': finding.get(rec.record_id),
                      'action': h[-1].action if h else None, 'previous_action_id': str(h[-1].id) if h else None,
                      'history': [{'id': str(a.id), 'action': a.action, 'note': a.note, 'actor_id': str(a.user_id), 'created_at': a.created_at.isoformat()} for a in h]})
    counts = {k: sum(1 for i in items if i['action'] == k) for k in ('accept', 'reject', 'pending')} | {'no_action': sum(1 for i in items if not i['action'])}
    return {'batch_id': str(batch.id), 'run_id': str(run.id) if run else None, 'items': items, 'counts': counts,
            'notice': 'Rejected or pending invoices cannot be claimed this period; no action is treated as deemed accepted. This mapping is for CA review.'}

class ImsItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    record_id: UUID
    action: Literal['accept', 'reject', 'pending']
    previous_action_id: UUID | None = None

class ImsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[ImsItem] = Field(min_length=1, max_length=2000)
    note: str = Field(min_length=1, max_length=2000)

@router.post('/imports/{batch_id}/ims')
async def ims_act(batch_id: UUID, data: ImsInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not data.note.strip(): raise HTTPException(400, 'A note is required')
    batch = await _statement_batch(db, batch_id, org_id, lock=True)  # serialises concurrent reviewers
    records = {r.id: r for r in (await db.execute(select(ImportRecord).where(ImportRecord.batch_id == batch.id, ImportRecord.is_valid.is_(True)))).scalars().all()}
    history = await ims_state(db, batch.id)
    if len({i.record_id for i in data.items}) != len(data.items): raise HTTPException(400, 'Each invoice may appear once per request')
    for item in data.items:
        rec = records.get(item.record_id)
        if not rec: raise HTTPException(404, 'Invoice not found in this statement')
        h = history.get(rec.record_id, [])
        if (h[-1].id if h else None) != item.previous_action_id: raise HTTPException(409, 'A newer IMS action exists. Reload before saving.')
    for item in data.items:
        db.add(ImsAction(record_id=item.record_id, user_id=user.id, action=item.action, note=data.note.strip()))
    tally = ', '.join(f'{a} {n}' for a in ('accept', 'reject', 'pending') if (n := sum(i.action == a for i in data.items)))
    audit(db, org_id, user.id, 'ims_action', 'import_batch', batch.id, batch.period_id, f'{len(data.items)} invoice(s): {tally}')
    await db.commit()
    return {'saved': len(data.items)}
