from io import BytesIO
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..dependencies import get_db, get_active_organization
from ...db.models import ReconciliationRun, FilingPeriod, GSTRegistration, Client
from ...services.review_service import result_views, record_views
from ...services.export_service import generate_excel_export

router = APIRouter(tags=["export"])

@router.get("/periods/{period_id}/reconciliation-runs/{run_id}/export")
async def export_run(period_id: UUID, run_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(ReconciliationRun, Client.id).join(FilingPeriod).join(GSTRegistration).join(Client).where(ReconciliationRun.id == run_id, FilingPeriod.id == period_id, Client.organization_id == org_id))).first()
    if not row:
        raise HTTPException(404, "Reconciliation run not found")
    run, client_id = row
    if run.status != "succeeded":
        raise HTTPException(400, "Cannot export incomplete or failed runs")
    cutoff = datetime.now(timezone.utc)
    data = {"run_id": str(run.id), "client_id": str(client_id), "period_id": str(run.period_id), "purchase_batch_id": str(run.purchase_batch_id), "statement_batch_id": str(run.statement_batch_id), "export_timestamp": cutoff.isoformat(), "review_cutoff": cutoff.isoformat(), "summary_data": run.summary_data, "results": await result_views(db, run.id, cutoff), "purchases": await record_views(db, run.purchase_batch_id), "statements": await record_views(db, run.statement_batch_id)}
    buffer = BytesIO()
    generate_excel_export(data, buffer)
    return Response(buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="GST_Reconciliation_{run_id}.xlsx"'})
