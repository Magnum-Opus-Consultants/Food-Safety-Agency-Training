from ninja import Router

from audit.models import AuditEntry
from core.api_support import Refusal, ok

router = Router(tags=["audit"])


@router.get("/audit")
def audit(request, screen: str | None = None, entityRef: str | None = None, take: int = 12):
    """The trail at the foot of each screen: the last N entries caused from that screen. Read only by
    directors and system administrators."""
    if not request.user.can_see_audit:
        raise Refusal("forbidden", ["The audit trail is available to directors and system administrators."],
                      "You do not have access to the audit trail.", status=403)
    qs = AuditEntry.objects.all()
    if screen:
        qs = qs.filter(screen=screen)
    if entityRef:
        qs = qs.filter(entity_ref=entityRef)
    return ok([e.as_dict() for e in qs[: max(1, min(take, 100))]])
