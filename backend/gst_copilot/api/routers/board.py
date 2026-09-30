"""The Board: per client-period status of each workstream, derived only from persisted workflow records."""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..dependencies import get_db, get_active_organization
from .sales import record_views as sales_record_views
from .worksheet import _draft_views, _itc_state
from ...db.models import Client, FilingPeriod, GSTRegistration, ImportBatch, ReconciliationRun, SalesBatch
from ...services.cache import cached

router = APIRouter(tags=['board'])

def cell(tone, label, target):
    # tone: done | action | blocked | waiting
    return {'tone': tone, 'label': label, 'target': target}

async def _sales_cell(db, period_id):
    batches = (await db.execute(select(SalesBatch).where(SalesBatch.period_id == period_id).order_by(SalesBatch.created_at.desc()))).scalars().all()
    if not batches: return cell('waiting', 'Awaiting sales file', 'sales')
    latest = batches[0]
    if latest.status != 'committed': return cell('action', 'Commit sales import', 'sales')
    rows = await sales_record_views(db, latest.id)
    pending = sum(1 for r in rows if r['decision'] == 'unresolved')
    return cell('action', f'{pending} sales row(s) to review', 'sales') if pending else cell('done', 'Sales reviewed', 'sales')

async def _purchase_cell(db, period_id):
    committed = {b.source_type for b in (await db.execute(select(ImportBatch).where(ImportBatch.period_id == period_id, ImportBatch.status == 'committed'))).scalars().all()}
    if {'purchase', 'statement'} - committed:
        uploaded = (await db.execute(select(ImportBatch.id).where(ImportBatch.period_id == period_id).limit(1))).first()
        return cell('action', 'Commit imports', 'workspace') if uploaded else cell('waiting', 'Awaiting purchase files', 'workspace')
    run = (await db.execute(select(ReconciliationRun).where(ReconciliationRun.period_id == period_id).order_by(ReconciliationRun.created_at.desc()).limit(1))).scalars().first()
    if not run: return cell('action', 'Run reconciliation', 'workspace')
    if run.status == 'failed': return cell('blocked', 'Reconciliation failed', 'workspace')
    if run.status != 'succeeded': return cell('waiting', 'Reconciliation running', 'workspace')
    results, history = await _itc_state(db, run)
    undecided = sum(1 for r in results if not history[r.result_id])
    return cell('action', f'{undecided} ITC decision(s) needed', 'worksheet') if undecided else cell('done', 'Reconciled · ITC decided', 'worksheet')

async def _worksheet_cell(db, period, org_id):
    drafts = await _draft_views(db, period, org_id)
    if not drafts: return cell('waiting', 'Not started', 'worksheet')
    latest = drafts[0]
    active = next((d for d in drafts if d['approval'] and not d['approval']['reopen']), None)
    if active:
        if active['state'] == 'approved_stale': return cell('blocked', 'Approval out of date', 'worksheet')
        if active['approval']['filing_evidence']: return cell('done', 'Filed (user-reported)', 'worksheet')
        return cell('done', 'Approved', 'worksheet')
    if latest['state'] == 'reopened': return cell('action', 'Reopened — redraft', 'worksheet')
    if latest['blockers']: return cell('action', 'Draft has blockers', 'worksheet')
    return cell('action', 'Ready for approval', 'worksheet')

@router.get('/board')
async def board(org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    return await cached(db, org_id, 'board', lambda: board_rows(db, org_id))

async def board_rows(db, org_id):
    rows =(await db.execute(select(FilingPeriod, GSTRegistration, Client).join(GSTRegistration, FilingPeriod.registration_id == GSTRegistration.id)
                             .join(Client, GSTRegistration.client_id == Client.id).where(Client.organization_id == org_id)
                             .order_by(FilingPeriod.period_code.desc(), Client.name))).all()
    # ponytail: computes every period on each request; add caching or a period filter when rosters grow past a few hundred periods.
    items = []
    for period, reg, client in rows:
        items.append({'period_id': str(period.id), 'period_code': period.period_code, 'client_id': str(client.id), 'client_name': client.name,
                      'registration': reg.gstin, 'sales': await _sales_cell(db, period.id), 'purchases': await _purchase_cell(db, period.id),
                      'worksheet': await _worksheet_cell(db, period, org_id)})
    return items
