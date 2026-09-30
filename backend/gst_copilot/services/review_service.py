"""Read-only, explicit projections of frozen records and review history."""
from sqlalchemy import select
from ..db.models import ImportRecord, ValidationIssue, ReconciliationRun, ReconciliationResult, ResultDifference, ExceptionResolution

def ids(value):
    if isinstance(value, dict):
        value = value.get("ids")
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError("Invalid persisted source-reference shape")
    return value

async def record_views(db, batch_id):
    records = (await db.execute(select(ImportRecord).where(ImportRecord.batch_id == batch_id).order_by(ImportRecord.row_number))).scalars().all()
    issues = (await db.execute(select(ValidationIssue).join(ImportRecord).where(ImportRecord.batch_id == batch_id))).scalars().all()
    return [{"record_id": r.raw_data.get("record_id", ""), "row_number": r.row_number, "is_valid": r.is_valid, "raw_data": r.raw_data, "issues": [v.reason for v in issues if v.record_id == r.id]} for r in records]

async def result_views(db, run_id, cutoff=None):
    run = await db.get(ReconciliationRun, run_id)
    purchases = await record_views(db, run.purchase_batch_id)
    statements = await record_views(db, run.statement_batch_id)
    results = (await db.execute(select(ReconciliationResult).where(ReconciliationResult.run_id == run_id).order_by(ReconciliationResult.result_id))).scalars().all()
    differences = (await db.execute(select(ResultDifference).join(ReconciliationResult).where(ReconciliationResult.run_id == run_id))).scalars().all()
    query = select(ExceptionResolution).where(ExceptionResolution.run_id == run_id)
    if cutoff is not None:
        query = query.where(ExceptionResolution.created_at <= cutoff)
    history = (await db.execute(query.order_by(ExceptionResolution.created_at, ExceptionResolution.id))).scalars().all()
    output = []
    for r in results:
        pids, sids = ids(r.purchase_record_ids), ids(r.statement_record_ids)
        events = [{"id": str(e.id), "decision": e.decision, "note": e.note, "actor_id": str(e.user_id), "created_at": e.created_at.isoformat()} for e in history if e.result_id == r.result_id]
        row = (r.validation_issues or {}).get("source_row_number") if isinstance(r.validation_issues, dict) else None
        if row is not None:
            # Validation errors link by physical row: their record_id may be blank or shared.
            p_evidence = [p for p in purchases if pids and p["row_number"] == row]
            s_evidence = [s for s in statements if sids and s["row_number"] == row]
        else:
            p_evidence = [p for p in purchases if p["record_id"] in pids]
            s_evidence = [s for s in statements if s["record_id"] in sids]
        output.append({"id": r.id, "result_id": r.result_id, "status": r.status, "reason": r.reason, "purchase_record_ids": pids, "statement_record_ids": sids, "purchase_records": p_evidence, "statement_records": s_evidence,"differences": {d.field_name: format(d.difference_value, '.2f') for d in differences if d.reconciliation_result_id == r.id}, "history": events, "review_status": events[-1]["decision"] if events else "unresolved"})
    # Reviewers read by record number; result_id (a hash) only breaks ties so the order stays deterministic.
    return sorted(output, key=lambda o: ((o["purchase_record_ids"] or o["statement_record_ids"] or [""])[0], o["result_id"]))
