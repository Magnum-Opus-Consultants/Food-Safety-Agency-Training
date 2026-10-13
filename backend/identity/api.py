import datetime as dt

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.db import transaction
from django.middleware.csrf import get_token
from ninja import Router, Schema

from audit.services import record
from core import clock
from core.credentials import username_for
from core.api_support import Refusal, iso, ok, require
from core.models import DemoClock
from identity.models import ROLE_LABEL, Account

router = Router(tags=["identity"])


def account_dict(a: Account):
    state, tone = a.display_state()
    reg = a.current_registration()
    return {
        "ref": a.reference,
        "name": a.display_name,
        "position": a.position,
        "role": a.hub_role,
        "roleLabel": ROLE_LABEL.get(a.hub_role, a.hub_role),
        "reportsTo": a.reports_to.display_name if a.reports_to_id else a.reports_to_label,
        "state": state,
        "tone": tone,
        "registration": {"type": reg.registration_type, "body": reg.body.name, "expiresOn": iso(reg.expires_on),
                         "standing": reg.standing()} if reg else None,
    }


@router.get("/auth/csrf", auth=None)
def csrf(request):
    return ok({"csrfToken": get_token(request)})


FAILED_LIMIT = 5
LOCKOUT_SECONDS = 15 * 60
BAD_CREDENTIALS = "The username or password is incorrect."


class Login(Schema):
    username: str
    password: str


@router.post("/auth/login", auth=None)
def sign_in(request, body: Login):
    """Username and password, checked against the hashed password. Five failures lock the
    username for fifteen minutes. Production replaces this with Microsoft Entra ID single sign-on."""
    typed = body.username.strip()
    # Accept "louis.visagie", "Louis.Visagie" or the name as written, "Louis Visagie".
    username = username_for(typed) if " " in typed else typed.lower()
    key = f"login-failures:{username}"
    if cache.get(key, 0) >= FAILED_LIMIT:
        raise Refusal("locked_out", ["Too many failed attempts. Try again in fifteen minutes."],
                      "Sign-in is temporarily locked for this username.", status=429)
    # Generated passwords never contain spaces, so stray whitespace from a paste is dropped.
    account = authenticate(request, username=username, password=body.password.strip())
    if account is None:
        cache.set(key, cache.get(key, 0) + 1, LOCKOUT_SECONDS)
        raise Refusal("bad_credentials", [BAD_CREDENTIALS], "Sign-in failed.", status=401)
    cache.delete(key)
    if account.is_suspended:
        # Status is revealed only after the password is proven.
        reason = account.suspended_reason or "the registration behind this role has lapsed"
        raise Refusal("account_suspended", [f"{account.display_name}’s account is suspended — {reason}."],
                      "Reinstatement requires a current registration on file.", status=403)
    login(request, account)
    with transaction.atomic():
        record(account, f"{account.display_name} signed in", account, screen="login")
    return ok(me_dict(account))


@router.post("/auth/logout")
def sign_out(request):
    logout(request)
    return ok({"signedOut": True})


def me_dict(a: Account):
    d = account_dict(a)
    d["segments"] = a.readable_segments()
    d["writes"] = [s for s in d["segments"] if a.can(s, write=True)]
    d["canMoveClock"] = settings.DEMO_MODE and a.hub_role in ("TrainingManager", "SystemAdministrator")
    d["canSeeAudit"] = a.can_see_audit
    d["canSeeDesk"] = a.can_see_desk
    return d


@router.get("/me")
def me(request):
    return ok(me_dict(request.user), today=clock.today().isoformat(), demo=settings.DEMO_MODE, clockMoved=clock.is_moved())


class ClockMove(Schema):
    days: int = 0
    reset: bool = False


@router.get("/clock")
def get_clock(request):
    return ok({"today": clock.today().isoformat(), "demo": settings.DEMO_MODE})


@router.post("/clock")
def move_clock(request, body: ClockMove):
    """Demo only: move the business date so the department can watch triggers fire."""
    if not (settings.DEMO_MODE and request.user.hub_role in ("TrainingManager", "SystemAdministrator")):
        raise Refusal("forbidden", ["Only the training manager can move the demo clock."], "Not permitted.", status=403)
    if not -31 <= body.days <= 31:
        raise Refusal("bad_step", ["Move the clock by at most 31 days at a time."], "Step too large.")
    with transaction.atomic():
        before = clock.today()
        if body.reset:
            DemoClock.objects.filter(pk=1).delete()
            after = clock.today()
            what = f"Demo clock returned from {before.isoformat()} to today, {after.isoformat()}"
        else:
            row, _ = DemoClock.objects.get_or_create(pk=1, defaults={"today": before})
            row.today = before + dt.timedelta(days=body.days)
            row.save()
            after = row.today
            what = f"Demo clock moved from {before.isoformat()} to {after.isoformat()}"
        audit = record(request.user, what, screen=request.headers.get("X-FSA-Screen", ""))
    return ok({"today": after.isoformat(), "moved": clock.is_moved()}, audit=audit)


@router.get("/users")
def users(request):
    require(request, "admin")
    accounts = Account.objects.filter(is_active=True).select_related("reports_to").prefetch_related("registrations__body", "segments__segment")
    rows = []
    for a in accounts:
        d = account_dict(a)
        d["segments"] = ", ".join(sorted(f"{s.segment.name}{' (own)' if s.scope == 'own' else ''}"
                                         f"{'' if s.access == 'write' else ' · read'}" for s in a.segments.all())) or "—"
        d["serviceAccount"] = a.is_service_account
        rows.append(d)
    return ok(rows, source="Accounts, segment grants and facilitator registrations")
