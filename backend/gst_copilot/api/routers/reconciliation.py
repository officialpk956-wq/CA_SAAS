from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import List

from ..dependencies import get_db, get_active_organization, get_current_user
from ..schemas import ReconciliationRunCreate, ReconciliationRunResponse, ReconciliationResultResponse
from ...db.models import FilingPeriod, GSTRegistration, Client, ImportBatch, ReconciliationRun, ReconciliationResult, ExceptionResolution, User
from ...services.audit import record as audit
from ...services.reconciliation_service import execute_run

router = APIRouter(tags=["reconciliation"])

@router.post("/periods/{period_id}/reconciliation-runs", response_model=ReconciliationRunResponse)
async def create_run(
    period_id: UUID,
    run_in: ReconciliationRunCreate,
    org_id: UUID = Depends(get_active_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Authorize period
    result = await db.execute(
        select(FilingPeriod)
        .join(GSTRegistration)
        .join(Client)
        .where(FilingPeriod.id == period_id, Client.organization_id == org_id)
    )
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Period not found")
        
    # Check imports exist and are committed
    batches_q = await db.execute(
        select(ImportBatch)
        .where(ImportBatch.id.in_([run_in.purchase_batch_id, run_in.statement_batch_id]), ImportBatch.period_id == period_id)
    )
    batches = {b.id: b for b in batches_q.scalars().all()}
    
    pb = batches.get(run_in.purchase_batch_id)
    sb = batches.get(run_in.statement_batch_id)
    
    if not pb or not sb:
        raise HTTPException(status_code=404, detail="One or more import batches not found")
    if pb.status != "committed" or sb.status != "committed":
        raise HTTPException(status_code=400, detail="Import batches must be committed")
        
    if pb.source_type != "purchase" or sb.source_type != "statement":
        raise HTTPException(status_code=400, detail="Must provide exactly one purchase and one statement batch")
        
    # Check idempotency: run already exists for these two batches
    existing_q = await db.execute(
        select(ReconciliationRun).where(
            ReconciliationRun.purchase_batch_id == pb.id,
            ReconciliationRun.statement_batch_id == sb.id,
            ReconciliationRun.status.in_(["pending", "running", "succeeded"])
        )
    )
    existing = existing_q.scalars().first()
    if existing:
        return existing
        
    run = ReconciliationRun(
        period_id=period_id,
        purchase_batch_id=pb.id,
        statement_batch_id=sb.id
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    
    # Synchronous bounded execution as per MVP requirements
    await execute_run(db, run.id)

    await db.refresh(run)
    audit(db, org_id, user.id, 'reconciliation_run', 'reconciliation_run', run.id, period_id, f'status {run.status}')
    await db.commit()
    await db.refresh(run)
    return run

@router.get("/periods/{period_id}/reconciliation-runs", response_model=List[ReconciliationRunResponse])
async def list_runs(period_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ReconciliationRun)
        .join(FilingPeriod).join(GSTRegistration).join(Client)
        .where(FilingPeriod.id == period_id, Client.organization_id == org_id)
        .order_by(ReconciliationRun.created_at.desc())
    )
    return result.scalars().all()

@router.get("/periods/{period_id}/reconciliation-runs/{run_id}", response_model=ReconciliationRunResponse)
async def get_run(period_id: UUID, run_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ReconciliationRun)
        .join(FilingPeriod).join(GSTRegistration).join(Client)
        .where(
            ReconciliationRun.id == run_id,
            FilingPeriod.id == period_id,
            Client.organization_id == org_id
        )
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Reconciliation run not found")
    return run

@router.get("/periods/{period_id}/reconciliation-runs/{run_id}/results", response_model=List[ReconciliationResultResponse])
async def get_run_results(period_id: UUID, run_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    # Auth: verify run belongs to org
    run_q = await db.execute(
        select(ReconciliationRun)
        .join(FilingPeriod).join(GSTRegistration).join(Client)
        .where(ReconciliationRun.id == run_id, FilingPeriod.id == period_id, Client.organization_id == org_id)
    )
    if not run_q.scalars().first():
        raise HTTPException(status_code=404, detail="Reconciliation run not found")

    from ...services.review_service import result_views
    return await result_views(db, run_id)
