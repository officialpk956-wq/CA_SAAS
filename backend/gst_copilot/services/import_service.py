import hashlib
import uuid
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..db.models import SourceFile, ImportBatch, ImportRecord, ValidationIssue
from ..parser import parse_purchases, parse_statements, ParserError
from ..validation import validate_row

async def process_upload(
    db: AsyncSession,
    org_id: uuid.UUID,
    period_id: uuid.UUID,
    source_type: str,
    original_filename: str,
    file_content: bytes,
    storage_dir: str,
    valid_suppliers: set
) -> ImportBatch:
    # 1. Store privately and hash
    content_hash = hashlib.sha256(file_content).hexdigest()
    
    # Check idempotency: same org, period, source_type, and file hash
    # To do this correctly: look for an existing ImportBatch for this period + source_type 
    # linked to a SourceFile with this hash.
    # We allow same hash to be uploaded if it was just "preview" maybe?
    # Requirement: "An identical file uploaded for the same organization, registration, period, and source type should return the existing import rather than create duplicate committed data."
    existing_q = await db.execute(
        select(ImportBatch)
        .join(SourceFile)
        .where(
            ImportBatch.period_id == period_id,
            ImportBatch.source_type == source_type,
            SourceFile.content_hash == content_hash,
            SourceFile.organization_id == org_id
        )
    )
    existing_batch = existing_q.scalars().first()
    if existing_batch:
        return existing_batch
    
    storage_path = Path(storage_dir) / org_id.hex / f"{uuid.uuid4().hex}.csv"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(storage_path, 'wb') as f:
        f.write(file_content)
        
    source_file = SourceFile(
        organization_id=org_id,
        original_filename=original_filename,
        storage_path=str(storage_path),
        content_hash=content_hash,
        size_bytes=len(file_content)
    )
    db.add(source_file)
    await db.flush()
    
    batch = ImportBatch(
        period_id=period_id,
        source_file_id=source_file.id,
        source_type=source_type,
        status="preview",
        record_count=0,
        invalid_count=0
    )
    db.add(batch)
    await db.flush()
    
    # 2. Parse using Phase 2 engine
    try:
        if source_type == "purchase":
            source_rows = parse_purchases(str(storage_path))
        elif source_type == "statement":
            source_rows = parse_statements(str(storage_path))
        else:
            raise ValueError(f"Unknown source type: {source_type}")
    except (ParserError, UnicodeError) as e:
        await db.rollback()
        storage_path.unlink(missing_ok=True)
        detail = str(e).replace(str(storage_path), "uploaded CSV")
        raise ValueError(f"Parsing error: {detail}")

    try:
        return await _store_records(db, batch, source_rows, valid_suppliers)
    except Exception:
        # A rejected file must not leave its stored copy behind.
        await db.rollback()
        storage_path.unlink(missing_ok=True)
        raise


async def _store_records(db: AsyncSession, batch: ImportBatch, source_rows, valid_suppliers: set) -> ImportBatch:
    if len(source_rows) > 10000:
        raise ValueError("File exceeds 10,000 data rows")

    # 3. Validate
    invalid_count = 0
    record_count = len(source_rows)
    
    # Uniqueness check across the file
    seen_ids = set()
    for row in source_rows:
        rid = row.raw_data.get("record_id", "").strip()
        if rid:
            if rid in seen_ids:
                raise ValueError(f"Duplicate record ID '{rid}' found.")
            seen_ids.add(rid)

    for row in source_rows:
        val_res = validate_row(row, valid_suppliers)
        is_valid = not hasattr(val_res, 'reason') # ValidatedInvoice doesn't have reason
        
        record = ImportRecord(
            batch_id=batch.id,
            row_number=row.row_number,
            is_valid=is_valid,
            raw_data=row.raw_data,
        )
        if is_valid:
            record.record_id = val_res.record_id
            record.document_type = val_res.document_type
            record.supplier_ref = val_res.supplier_ref
            record.invoice_number = val_res.invoice_number
            record.invoice_date = val_res.invoice_date
            record.taxable_value = val_res.taxable_value
            record.cgst = val_res.cgst
            record.sgst = val_res.sgst
            record.igst = val_res.igst
            record.cess = val_res.cess
            record.invoice_total = val_res.invoice_total
        else:
            invalid_count += 1
            
        db.add(record)
        
        # We need to add validation issue if invalid
        # But we need record.id which is generated after flush
        
    batch.record_count = record_count
    batch.invalid_count = invalid_count
    
    await db.flush()
    
    # Re-iterate to add validation issues (since now records have IDs)
    # SQLAlchemy requires flushing or we can just associate them via object relationships.
    # Since we didn't setup bidirectional relationships, we flush.
    
    # Re-evaluating is slow, but this is MVP and data is small
    # Let's map issues to row numbers
    issues_to_add = []
    
    # We can fetch the records we just added
    records_q = await db.execute(select(ImportRecord).where(ImportRecord.batch_id == batch.id))
    records = {r.row_number: r for r in records_q.scalars().all()}
    
    for row in source_rows:
        val_res = validate_row(row, valid_suppliers)
        if hasattr(val_res, 'reason'):
            rec = records[row.row_number]
            issues_to_add.append(ValidationIssue(
                record_id=rec.id,
                reason=val_res.reason
            ))
            
    db.add_all(issues_to_add)
    await db.commit()
    await db.refresh(batch)
    
    return batch
