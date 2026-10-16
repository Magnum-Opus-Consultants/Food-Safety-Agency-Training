"""Managing staff accounts: add, change role and access, suspend or reinstate, reset a password.

Users are managed by managers and above: the head of department (the training manager), the
directors, and the system administrator.
Each role starts from a default set of segment grants; the grants can then be adjusted per person.
Every change is audited with its old and new values. A password is shown once to whoever set it and
is never written to the audit trail. Nobody changes their own role or access, or suspends themself."""

import re

from django.conf import settings
from django.db import transaction

from audit.services import record
from core import clock
from core.api_support import Refusal
from core.credentials import LOGINS_FILE, new_password, username_for
from identity.models import ROLE_LABEL, Account, AccountSegment, Segment

MANAGERS = ("TrainingManager", "Director", "SystemAdministrator")
# Who may give the senior roles: a director is appointed by a director or the system administrator;
# a system administrator only by the system administrator.
GIVES_RESTRICTED = {"Director": ("Director", "SystemAdministrator"), "SystemAdministrator": ("SystemAdministrator",)}
STAFF_ROLES = ["TrainingManager", "EnquiryHandler", "Facilitator", "Assessor", "Moderator", "Director", "SystemAdministrator"]
RESTRICTED_ROLES = ("Director", "SystemAdministrator")

# The access each role starts with: segment -> (access, scope). Directors read everything by role.
ROLE_DEFAULTS = {
    "TrainingManager": {s: ("write", "all") for s in ("overview", "demand", "courses", "delivery", "learners", "results", "moderation",
                                                      "certification", "assurance", "depository", "reporting")},
    "EnquiryHandler": {"demand": ("write", "all"), "learners": ("write", "all"), "depository": ("write", "all"),
                       "courses": ("read", "all"), "delivery": ("read", "all"), "assurance": ("read", "all")},
    "Facilitator": {"delivery": ("write", "own"), "results": ("write", "own"), "courses": ("read", "all")},
    "Assessor": {"delivery": ("write", "own"), "results": ("write", "own"), "courses": ("read", "all")},
    "Moderator": {"moderation": ("write", "all"), "results": ("read", "all"), "courses": ("read", "all"), "assurance": ("read", "all")},
    "Director": {},
    "SystemAdministrator": {"admin": ("write", "all")},
}


def can_manage(actor) -> bool:
    return actor.hub_role in MANAGERS and not actor.is_service_account


def _guard(actor, target=None, role=None):
    if not can_manage(actor):
        raise Refusal("forbidden", ["Users are managed by the head of department (the training manager), the directors "
                                    "and the system administrator."],
                      "Not permitted.", status=403)
    if target is not None and target.is_service_account:
        raise Refusal("service_account", [f"{target.display_name} is a service account for the HR Hub link; it is not managed here."],
                      "Not editable here.")
    restricted = [r for r in (role, target.hub_role if target else None) if r in RESTRICTED_ROLES]
    for r in restricted:
        if actor.hub_role not in GIVES_RESTRICTED[r]:
            who = "a director or the system administrator" if r == "Director" else "the system administrator"
            raise Refusal("forbidden", [f"Only {who} gives or changes the {ROLE_LABEL[r].lower()} role."], "Not permitted.", status=403)


def _grants_text(account) -> str:
    rows = sorted(account.segments.select_related("segment"), key=lambda x: x.segment.name)
    return ", ".join(f"{x.segment.name} ({x.access}{', own' if x.scope == 'own' else ''})" for x in rows) or "role default (reads by role)"


def _set_grants(actor, account, grants: dict[str, tuple[str, str]]):
    known = set(Segment.objects.values_list("code", flat=True))
    account.segments.all().delete()
    for code, (access, scope) in grants.items():
        if code in known and access in ("read", "write"):
            AccountSegment.objects.create(account=account, segment_id=code, access=access, scope=scope if scope in ("all", "own") else "all",
                                          granted_by=actor if getattr(actor, "pk", None) else None)


def _unique_username(name: str) -> str:
    base = username_for(name) or "user"
    candidate, n = base, 2
    while Account.objects.filter(username__iexact=candidate).exists():
        candidate, n = f"{base}{n}", n + 1
    return candidate


def _save_demo_login(account, password):
    """In the demo, keep demo-logins.txt in step so testers can sign in as the new or reset user."""
    if not settings.DEMO_MODE or not getattr(settings, "DEMO_LOGINS_FILE_WRITES", True):
        return
    text = LOGINS_FILE.read_text(encoding="utf-8") if LOGINS_FILE.exists() else ""
    pattern = re.compile(rf"(Username:\s*{re.escape(account.username)}\s*\n\s*Password:\s*)\S+")
    if pattern.search(text):
        text = pattern.sub(lambda m: m.group(1) + password, text)
    else:
        text += (f"\n{account.display_name} — {ROLE_LABEL.get(account.hub_role, account.hub_role)}\n  {account.position}\n"
                 f"  Username: {account.username}\n  Password: {password}\n")
    LOGINS_FILE.write_text(text, encoding="utf-8")


@transaction.atomic
def create_user(actor, *, name, email, position, role, reports_to_ref="", screen="users"):
    _guard(actor, role=role)
    reasons = [] if (name or "").strip() else ["Give the person's full name."]
    if role not in STAFF_ROLES:
        reasons.append("Choose the person's role.")
    if (email or "").strip() and "@" not in email:
        reasons.append(f"{email.strip()} is not an email address.")
    elif (email or "").strip() and Account.objects.filter(email__iexact=email.strip()).exists():
        reasons.append(f"{email.strip()} already belongs to another user.")
    if not (position or "").strip():
        reasons.append("Give the person's position, for example 'Facilitator — IMI and Classification'.")
    manager = Account.objects.filter(reference=reports_to_ref, is_active=True).first() if reports_to_ref else None
    if reports_to_ref and manager is None:
        reasons.append("Choose who the person reports to from the list.")
    if reasons:
        raise Refusal("invalid", reasons, "The user cannot be added yet.", status=422)
    n = Account.objects.count() + 1
    reference = f"USR-{n:04d}"
    while Account.objects.filter(reference=reference).exists():
        n += 1
        reference = f"USR-{n:04d}"
    password = new_password()
    account = Account(reference=reference, username=_unique_username(name), display_name=name.strip(), position=position.strip(),
                      hub_role=role, email=(email or "").strip(), reports_to=manager, created_by=actor, modified_by=actor)
    account.set_password(password)
    account.save()
    _set_grants(actor, account, ROLE_DEFAULTS.get(role, {}))
    _save_demo_login(account, password)
    audit = record(actor, f"User {account.reference} {account.display_name} added as {ROLE_LABEL[role].lower()} "
                          f"(username {account.username}) with the role's default access", account, screen=screen,
                   after={"Role": ROLE_LABEL[role], "Position": account.position, "Access": _grants_text(account)})
    return account, password, audit


@transaction.atomic
def update_user(actor, account, *, position=None, email=None, role=None, reports_to_ref=None, grants=None, screen="users"):
    """grants: {segment: [access, scope]} to set the access exactly, or None to leave it. Changing the
    role without grants resets the access to the new role's default."""
    _guard(actor, account, role=role)
    if account.pk == actor.pk and (role not in (None, account.hub_role) or grants is not None):
        raise Refusal("own_account", ["You cannot change your own role or access; ask another manager."], "Not permitted.", status=403)
    before = {"Role": ROLE_LABEL[account.hub_role], "Position": account.position, "Email": account.email,
              "Reports to": account.reports_to.display_name if account.reports_to_id else account.reports_to_label,
              "Access": _grants_text(account)}
    reasons = []
    if role is not None and role not in STAFF_ROLES:
        reasons.append("Choose a role from the list.")
    if email is not None and email.strip() and "@" not in email:
        reasons.append(f"{email.strip()} is not an email address.")
    if position is not None and not position.strip():
        reasons.append("The position cannot be blank.")
    manager = None
    if reports_to_ref:
        manager = Account.objects.filter(reference=reports_to_ref, is_active=True).exclude(pk=account.pk).first()
        if manager is None:
            reasons.append("Choose who the person reports to from the list.")
    if reasons:
        raise Refusal("invalid", reasons, f"{account.display_name} cannot be saved yet.", status=422)
    if position is not None:
        account.position = position.strip()
    if email is not None:
        account.email = email.strip()
    if reports_to_ref is not None:
        account.reports_to = manager
    role_changed = role is not None and role != account.hub_role
    if role is not None:
        account.hub_role = role
    account.modified_by = actor
    account.save()
    if grants is not None:
        _set_grants(actor, account, {k: (v[0], v[1] if len(v) > 1 else "all") for k, v in grants.items() if v and v[0] in ("read", "write")})
    elif role_changed:
        _set_grants(actor, account, ROLE_DEFAULTS.get(role, {}))
    account = Account.objects.get(pk=account.pk)
    after = {"Role": ROLE_LABEL[account.hub_role], "Position": account.position, "Email": account.email,
             "Reports to": account.reports_to.display_name if account.reports_to_id else account.reports_to_label,
             "Access": _grants_text(account)}
    changed = [k for k in after if after[k] != before[k]]
    if not changed:
        raise Refusal("no_change", ["Nothing was changed."], "There is nothing to save.")
    # The access lists can be long: the sentence names the change, the entry's before/after holds the detail.
    summary = "; ".join("access changed" if k == "Access" else f"{k.lower()} {before[k] or '—'} → {after[k] or '—'}" for k in changed)
    return account, record(actor, f"{account.display_name} ({account.reference}) changed — {summary}", account, screen=screen,
                           before={k: before[k] for k in changed}, after={k: after[k] for k in changed})


@transaction.atomic
def suspend(actor, account, reason, screen="users"):
    _guard(actor, account)
    if account.pk == actor.pk:
        raise Refusal("own_account", ["You cannot suspend your own account."], "Not permitted.", status=403)
    if not (reason or "").strip():
        raise Refusal("reason_needed", ["Give the reason for suspending the account."], "A reason is needed.", status=422)
    if account.state == "Suspended":
        raise Refusal("already", [f"{account.display_name} is already suspended."], "Nothing to change.")
    account.state, account.suspended_reason, account.suspended_at = "Suspended", reason.strip(), clock.now()
    account.modified_by = actor
    account.save()
    return record(actor, f"{account.display_name} ({account.reference}) suspended — {reason.strip()}", account, screen=screen,
                  before={"State": "Active"}, after={"State": "Suspended"})


@transaction.atomic
def reinstate(actor, account, screen="users"):
    _guard(actor, account)
    if account.state != "Suspended" and account.registration_standing() != "Lapsed":
        raise Refusal("already", [f"{account.display_name} is not suspended."], "Nothing to change.")
    if account.registration_standing() == "Lapsed":
        raise Refusal("registration_lapsed", [f"{account.display_name}'s registration has lapsed. Record the renewal on "
                                              "Facilitators & accreditation; the account is reinstated with it."], "Renew the registration first.")
    account.state, account.suspended_reason, account.suspended_at = "Active", "", None
    account.modified_by = actor
    account.save()
    return record(actor, f"{account.display_name} ({account.reference}) reinstated", account, screen=screen,
                  before={"State": "Suspended"}, after={"State": "Active"})


@transaction.atomic
def reset_password(actor, account, screen="users"):
    _guard(actor, account)
    password = new_password()
    account.set_password(password)
    account.modified_by = actor
    account.save()
    _save_demo_login(account, password)
    return password, record(actor, f"Password reset for {account.display_name} ({account.reference})", account, screen=screen)
