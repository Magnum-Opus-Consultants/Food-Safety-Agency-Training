"""Response envelope, refusals and access checks shared by every router."""
from ninja.errors import HttpError


class Refusal(Exception):
    """A blocked transition. The UI renders blockedBy verbatim (rule 2: name what is outstanding)."""

    def __init__(self, error: str, blocked_by: list[str], message: str, status: int = 409):
        super().__init__(message)
        self.error = error
        self.blocked_by = blocked_by
        self.message = message
        self.status = status

    def body(self):
        return {"error": self.error, "blockedBy": self.blocked_by, "message": self.message}


def ok(data, audit=None, **meta):
    """All responses carry { data, meta }; mutations add the audit entry they wrote."""
    if audit is not None:
        meta["audit"] = audit.as_dict()
    return {"data": data, "meta": meta}


def require(request, segment: str, write: bool = False, message: str | None = None):
    """The client is not the gate: every endpoint checks segment access here."""
    if not request.user.can(segment, write=write):
        raise Refusal(
            "forbidden",
            [message or f"Your role does not have {'write' if write else 'read'} access to {segment}."],
            "You do not have access to this action.",
            status=403,
        )


def not_found(what: str):
    raise HttpError(404, f"{what} not found")


def stamp(value, fmt="%Y-%m-%d %H:%M"):
    """A moment as shown on screen: South African local time, never UTC."""
    from django.utils import timezone

    return timezone.localtime(value).strftime(fmt) if value else None


def iso(value):
    return value.isoformat() if value else None
