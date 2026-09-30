from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import List

from ..dependencies import get_db, get_current_user, get_active_organization
from ...services.audit import record as audit
from ..schemas import ResolutionCreate, ResolutionResponse
from ...db.models import ReconciliationRun, ReconciliationResult, ExceptionResolution, User, FilingPeriod, GSTRegistration, Client

router = APIRouter(tags=["resolutions"])

@router.post("/runs/{run_id}/results/{result_id}/resolve", response_model=ResolutionResponse)
async def resolve_exception(
    run_id: UUID,
    result_id: str,
    res_in: ResolutionCreate,
    current_user: User = Depends(get_current_user),
    org_id: UUID = Depends(get_active_organization),
    db: AsyncSession = Depends(get_db)
):
    if res_in.decision not in ("investigating", "explained", "correction_required", "unresolved"):
        raise HTTPException(status_code=400, detail="Invalid decision")
        
    if not res_in.note.strip():
        raise HTTPException(400, "A nonblank review note is required")

    # Check authorization for the run
    run_q = await db.execute(
        select(ReconciliationRun)
        .join(FilingPeriod).join(GSTRegistration).join(Client)
        .where(ReconciliationRun.id == run_id, Client.organization_id == org_id)
    )
    run = run_q.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Reconciliation run not found")
        
    # Check result exists
    res_q = await db.execute(
        select(ReconciliationResult).where(
            ReconciliationResult.run_id == run_id,
            ReconciliationResult.result_id == result_id
        )
    )
    result_row = res_q.scalars().first()
    if not result_row:
        raise HTTPException(status_code=404, detail="Result not found")
        
    if result_row.status in ("matched",):
        raise HTTPException(status_code=400, detail="Cannot resolve a successful match")
        
    resolution = ExceptionResolution(
        run_id=run_id,
        result_id=result_id,
        user_id=current_user.id,
        decision=res_in.decision,
        note=res_in.note
    )
    db.add(resolution)
    await db.flush()
    audit(db, org_id, current_user.id, 'exception_' + res_in.decision, 'exception_resolution', resolution.id, run.period_id, f'result {result_id}')
    await db.commit()
    await db.refresh(resolution)
    return resolution
