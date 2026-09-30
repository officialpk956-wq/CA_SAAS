from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import List

from ..dependencies import get_db, get_active_organization, get_current_user
from ..schemas import ImportBatchResponse
from ...db.models import FilingPeriod, GSTRegistration, Client, ImportBatch, ImportRecord, ValidationIssue, User
from ...services.audit import record as audit
from ...services.import_service import process_upload
from ...config import settings
from ...parser import parse_suppliers # Assuming supplier seed file is used

router = APIRouter(tags=["imports"])

@router.post("/periods/{period_id}/imports", response_model=ImportBatchResponse)
async def create_import(
    period_id: UUID, 
    source_type: str, 
    file: UploadFile = File(...),
    org_id: UUID = Depends(get_active_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if source_type not in ("purchase", "statement"):
        raise HTTPException(status_code=400, detail="source_type must be purchase or statement")
        
    # Check limit (5MiB)
    contents = await file.read(5 * 1024 * 1024 + 1)
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File size exceeds 5MiB limit")
        
    # Authorize period
    result = await db.execute(
        select(FilingPeriod)
        .join(GSTRegistration)
        .join(Client)
        .where(FilingPeriod.id == period_id, Client.organization_id == org_id)
    )
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Period not found")
        
    # For MVP, suppliers are loaded from the static seed file
    # We should really load them from a DB, but the instructions say "Seed the fictional supplier references... not hidden app-startup mutations."
    # We will just parse them here from the sample data.
    from pathlib import Path
    sup_file = Path(__file__).resolve().parents[4] / "sample_data/v1/suppliers.csv"
    valid_suppliers = parse_suppliers(sup_file)

    try:
        batch = await process_upload(
            db=db,
            org_id=org_id,
            period_id=period_id,
            source_type=source_type,
            original_filename=file.filename or "unknown.csv",
            file_content=contents,
            storage_dir=settings.STORAGE_DIR,
            valid_suppliers=valid_suppliers
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit(db, org_id, user.id, 'import_uploaded', 'import_batch', batch.id, period_id, f'{source_type}: {batch.record_count} rows, {batch.invalid_count} invalid')
    await db.commit()
    return batch

@router.get("/periods/{period_id}/imports", response_model=List[ImportBatchResponse])
async def list_imports(period_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ImportBatch)
        .join(FilingPeriod).join(GSTRegistration).join(Client)
        .where(FilingPeriod.id == period_id, Client.organization_id == org_id)
        .order_by(ImportBatch.created_at.desc())
    )
    return result.scalars().all()

@router.post("/imports/{import_id}/commit", response_model=ImportBatchResponse)
async def commit_import(import_id: UUID, acknowledge_invalid: bool = False, note: str = "", org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ImportBatch)
        .join(FilingPeriod).join(GSTRegistration).join(Client)
        .where(ImportBatch.id == import_id, Client.organization_id == org_id)
    )
    batch = result.scalars().first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import not found")
        
    if batch.status == "committed":
        return batch # Idempotent
        
    if batch.invalid_count > 0 and not acknowledge_invalid:
        raise HTTPException(status_code=400, detail="Import contains invalid rows. Acknowledge them to commit.")
        
    if batch.invalid_count > 0 and not note.strip():
        raise HTTPException(status_code=400, detail="An acknowledgement note is required for invalid rows.")
    batch.commit_note = note.strip() or None
    batch.status = "committed"
    audit(db, org_id, user.id, 'import_committed', 'import_batch', batch.id, batch.period_id, f'{batch.source_type}; invalid rows acknowledged: {batch.invalid_count}')
    await db.commit()
    await db.refresh(batch)
    return batch

@router.get("/imports/{import_id}/rows")
async def import_rows(import_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    batch = (await db.execute(select(ImportBatch).join(FilingPeriod).join(GSTRegistration).join(Client).where(ImportBatch.id == import_id, Client.organization_id == org_id))).scalars().first()
    if not batch:
        raise HTTPException(404, "Import not found")
    from ...services.review_service import record_views
    records = await record_views(db, batch.id)
    return {"total": len(records), "items": records[offset:offset+limit]}
