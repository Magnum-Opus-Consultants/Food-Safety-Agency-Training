from django.db import connection

from audit.models import AuditEntry
from core import clock


def record(actor, what: str, obj=None, screen: str = "", before=None, after=None) -> AuditEntry:
    """Write the audit entry for a state change. Call inside the change's transaction."""
    if not connection.in_atomic_block:
        raise RuntimeError("Audit entries must be written inside the transaction that made the change")
    return AuditEntry.objects.create(
        at=clock.now(),
        actor=actor if getattr(actor, "pk", None) else None,
        actor_name=getattr(actor, "display_name", "System"),
        actor_role=getattr(actor, "hub_role", "System"),
        what=what,
        entity_type=obj._meta.label_lower if obj is not None else "",
        entity_ref=getattr(obj, "reference", "") if obj is not None else "",
        screen=screen,
        before=before,
        after=after,
    )
