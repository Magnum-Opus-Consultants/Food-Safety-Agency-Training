from ninja import Router

from audit.models import AuditEntry
from core.api_support import ok

router = Router(tags=["audit"])


@router.get("/audit")
def audit(request, screen: str | None = None, entityRef: str | None = None, take: int = 12):
    """The trail at the foot of each screen: the last N entries caused from that screen."""
    qs = AuditEntry.objects.all()
    if screen:
        qs = qs.filter(screen=screen)
    if entityRef:
        qs = qs.filter(entity_ref=entityRef)
    return ok([e.as_dict() for e in qs[: max(1, min(take, 100))]])
