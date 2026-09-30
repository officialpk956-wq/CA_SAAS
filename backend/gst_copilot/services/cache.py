"""Per-organization cache for expensive read models (Board, brief, savings).

Invalidation: every state-changing action writes an audit event, so the (count, latest time) of the
organization's audit events changes whenever anything these views depend on changes. A cached value is
reused only while that marker is unchanged.
"""
from sqlalchemy import func, select
from ..db.models import AuditEvent

# ponytail: in-process dict; each API worker keeps its own copy. Move to a shared cache (e.g. Redis) only if
# several workers serve one firm and the recompute cost matters.
_store: dict = {}
MAX_ENTRIES = 2000

async def audit_marker(db, org_id):
    count, latest = (await db.execute(select(func.count(AuditEvent.id), func.max(AuditEvent.created_at)).where(AuditEvent.organization_id == org_id))).one()
    return count, latest

async def cached(db, org_id, name, compute, *extra):
    marker = await audit_marker(db, org_id)
    key = (str(org_id), name, *extra)
    hit = _store.get(key)
    if hit and hit[0] == marker:
        return hit[1]
    value = await compute()
    if len(_store) >= MAX_ENTRIES: _store.clear()
    _store[key] = (marker, value)
    return value

def clear():
    _store.clear()
