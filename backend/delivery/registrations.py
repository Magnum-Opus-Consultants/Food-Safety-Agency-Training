"""Facilitator registrations: recording a new or renewed registration, with its certificate.

A registration is never edited: a renewal is a new registration row, so the history of who was
registered when stays intact. Recording a current registration for an account that was suspended
because its registration lapsed lifts the suspension. The certificate is kept in the private file
store, like Grade 10 evidence, and listed in the evidence library."""

import datetime as dt
import hashlib
from pathlib import Path

from django.conf import settings
from django.db import transaction

from assurance.models import Document, Library
from audit.services import record
from core import clock
from core.api_support import Refusal
from core.models import Body
from identity.models import Account, FacilitatorRegistration
from learners.evidence import MEDIA_TYPE, _sniff

ENTITY_TYPE = "identity.registration"


def _planner(actor):
    if actor.hub_role not in ("TrainingManager", "SystemAdministrator"):
        raise Refusal("forbidden", ["Facilitator registrations are recorded by the head of department (the training manager)."],
                      "Not permitted.", status=403)


def certificate(reg) -> Document | None:
    return Document.objects.filter(is_active=True, entity_type=ENTITY_TYPE, entity_ref=str(reg.pk)).first()


def path_of(doc: Document) -> Path:
    return Path(settings.FSA_FILE_ROOT) / doc.storage_key


@transaction.atomic
def record_registration(actor, account, *, registration_type, body_code, number, issued_on, expires_on, screen="facilitators"):
    _planner(actor)
    reasons = []
    if not (registration_type or "").strip():
        reasons.append("Name the registration, for example 'Assessor — meat examination'.")
    body = Body.objects.filter(code=body_code).first()
    if body is None:
        reasons.append("Choose the registering body.")
    if expires_on is None:
        reasons.append("Give the expiry date.")
    elif issued_on is not None and expires_on <= issued_on:
        reasons.append("The expiry date must be after the issue date.")
    elif expires_on < clock.today():
        reasons.append("That registration has already expired; record the current one.")
    if reasons:
        raise Refusal("invalid", reasons, "The registration cannot be recorded yet.", status=422)
    previous = account.current_registration()
    reg = FacilitatorRegistration.objects.create(
        account=account, registration_type=registration_type.strip(), body=body, registration_no=(number or "").strip(),
        issued_on=issued_on, expires_on=expires_on, created_by=actor, modified_by=actor,
    )
    lifted = ""
    if account.state == "Suspended" and reg.standing() != "Lapsed":
        account.state, account.suspended_reason, account.suspended_at = "Active", "", None
        account.save(update_fields=["state", "suspended_reason", "suspended_at"])
        lifted = "; suspension lifted"
    verb = "renewed" if previous else "recorded"
    what = (f"{account.display_name}: {reg.registration_type} ({body.name}) {verb}, valid to {expires_on.isoformat()}"
            + (f" (was {previous.expires_on.isoformat()})" if previous else "") + lifted)
    return reg, record(actor, what, account, screen=screen,
                       before={"Expires": previous.expires_on.isoformat()} if previous else None,
                       after={"Registration": reg.registration_type, "Body": body.name, "Expires": expires_on.isoformat()})


@transaction.atomic
def attach_certificate(actor, reg, filename: str, content: bytes, screen="facilitators"):
    _planner(actor)
    if not content:
        raise Refusal("invalid", ["The file is empty."], "Choose the certificate.", status=422)
    if len(content) > settings.FSA_UPLOAD_MAX_BYTES:
        raise Refusal("invalid", ["The file is larger than 5 MB."], "The file is too large.", status=422)
    ext = _sniff(content[:8])
    if ext is None:
        raise Refusal("invalid", ["Upload a PDF, or a photo or scan as JPG or PNG."], "That file type is not accepted.", status=422)
    digest = hashlib.sha256(content).hexdigest()
    key = f"evidence/registrations/{reg.account.reference}-{reg.pk}-{digest[:12]}.{ext}"
    target = Path(settings.FSA_FILE_ROOT) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    old = certificate(reg)
    if old:
        old.is_active, old.state, old.modified_by = False, "Archived", actor
        old.save()
    name = Path(filename or f"certificate.{ext}").name[:120]
    doc = Document.objects.create(
        library=Library.objects.get(code="evidence"), title=f"Registration certificate — {reg.account.display_name} · {name}",
        entity_type=ENTITY_TYPE, entity_ref=str(reg.pk), storage_key=key, sha256=digest, state="Held",
        created_by=actor, modified_by=actor,
    )
    return doc, record(actor, f"{reg.account.display_name}: certificate for {reg.registration_type} uploaded — {name} ({doc.reference})",
                       reg.account, screen=screen)


def media_type(doc: Document) -> str:
    return MEDIA_TYPE[doc.storage_key.rsplit(".", 1)[-1]]


def default_expiry(issued: dt.date | None) -> dt.date | None:
    return issued.replace(year=issued.year + 3) if issued else None
