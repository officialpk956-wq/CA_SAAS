"""Append-only audit events. Summaries are short descriptions; never secrets or full row contents."""
from ..db.models import AuditEvent

def record(db, org_id, user_id, action, resource_type, resource_id, period_id=None, summary=None):
    db.add(AuditEvent(organization_id=org_id, user_id=user_id, action=action, resource_type=resource_type,
                      resource_id=str(resource_id), period_id=period_id, summary=(summary or '')[:500] or None))
