"""IMS state for a statement import, shared by the IMS screen, ITC decisions, suggestions and the worksheet.

Workflow mapping (for CA review, not a statement of law): an invoice rejected or kept pending in IMS cannot be
claimed this period; an invoice with no action is treated as deemed accepted.
"""
from collections import defaultdict
from sqlalchemy import select
from ..db.models import ImportRecord, ImsAction

ACTIONS = ('accept', 'reject', 'pending')
NOT_CLAIMABLE = {'reject': 'rejected in IMS', 'pending': 'kept pending in IMS'}

async def ims_state(db, statement_batch_id):
    """{statement record_id (text): [ImsAction, ...] oldest first} for valid records of the batch."""
    rows = (await db.execute(select(ImsAction, ImportRecord.record_id).join(ImportRecord, ImsAction.record_id == ImportRecord.id)
                             .where(ImportRecord.batch_id == statement_batch_id).order_by(ImsAction.created_at, ImsAction.id))).all()
    history = defaultdict(list)
    for action, record_id in rows: history[record_id].append(action)
    return history

def latest(history, record_id):
    return history[record_id][-1].action if history.get(record_id) else None

def blocking(history, statement_ids):
    """The IMS reason a result cannot be claimed, or None."""
    for sid in statement_ids:
        reason = NOT_CLAIMABLE.get(latest(history, sid))
        if reason: return f'{sid} {reason}'
    return None
