"""The risk and escalation register: add a risk, keep it up to date, review it, link the complaints that show it
happening, and close it with a reason. A risk escalates by its rating (High) or when its trigger is breached;
every change is audited with its previous value."""

from django.db import transaction

from assurance.models import Risk
from audit.services import record
from core import clock
from core.api_support import Refusal

RATINGS = ("Low", "Medium", "High")


def _manager(actor):
    if not actor.can("assurance", write=True):
        raise Refusal("forbidden", ["The risk register is kept by the head of department and the directors."], "Not permitted.", status=403)


def _owner(ref):
    from identity.models import Account

    return Account.objects.filter(reference=ref, is_active=True, is_service_account=False).first() if ref else None


@transaction.atomic
def create(actor, *, risk, cause, rating, trigger, owner_ref, position="", screen="risk"):
    _manager(actor)
    owner = _owner(owner_ref)
    reasons = []
    if not (risk or "").strip():
        reasons.append("Describe the risk: what could happen.")
    if not (cause or "").strip():
        reasons.append("Give its cause.")
    if rating not in RATINGS:
        reasons.append("Rate it low, medium or high.")
    if not (trigger or "").strip():
        reasons.append("Name the trigger that escalates it: an event or a number, not a sentiment.")
    if owner is None:
        reasons.append("Choose the owner.")
    if reasons:
        raise Refusal("invalid", reasons, "The risk cannot be added yet.", status=422)
    r = Risk.objects.create(risk=risk.strip()[:300], cause=cause.strip()[:300], rating=rating, escalation_trigger=trigger.strip()[:300],
                            owner=owner, position=(position or "").strip()[:200], created_by=actor, modified_by=actor)
    return r, record(actor, f"{r.reference} risk added — {r.risk} ({rating}, owner {owner.display_name})", r, screen=screen)


@transaction.atomic
def update(actor, r, changes: dict, screen="risk"):
    _manager(actor)
    if not r.is_active:
        raise Refusal("closed", [f"{r.reference} was closed: {r.closed_reason}"], "Closed risks are kept as they were.")
    before, after, reasons = {}, {}, []
    labels = {"risk": "Risk", "cause": "Cause", "trigger": "Escalation trigger", "position": "Position"}
    fields = {"risk": "risk", "cause": "cause", "trigger": "escalation_trigger", "position": "position"}
    for key, field in fields.items():
        if key in changes:
            new = (changes[key] or "").strip()
            if key != "position" and not new:
                reasons.append(f"The {labels[key].lower()} cannot be blank.")
            elif new != getattr(r, field):
                before[labels[key]], after[labels[key]] = getattr(r, field), new
    if "rating" in changes and changes["rating"] != r.rating:
        if changes["rating"] not in RATINGS:
            reasons.append("Rate it low, medium or high.")
        else:
            before["Rating"], after["Rating"] = r.rating, changes["rating"]
    new_owner = r.owner
    if "ownerRef" in changes and changes["ownerRef"] != r.owner.reference:
        new_owner = _owner(changes["ownerRef"])
        if new_owner is None:
            reasons.append("Choose the owner from the list.")
        else:
            before["Owner"], after["Owner"] = r.owner.display_name, new_owner.display_name
    if "breached" in changes and bool(changes["breached"]) != (r.trigger_breached_at is not None):
        before["Trigger"], after["Trigger"] = ("Breached", "Not breached") if r.trigger_breached_at else ("Not breached", "Breached")
    if reasons:
        raise Refusal("invalid", reasons, f"{r.reference} cannot be saved yet.", status=422)
    if not after:
        raise Refusal("no_change", ["Nothing was changed."], "There is nothing to save.")
    for key, field in fields.items():
        if labels[key] in after:
            setattr(r, field, after[labels[key]][:300])
    if "Rating" in after:
        r.rating = after["Rating"]
    if "Owner" in after:
        r.owner = new_owner
    if "Trigger" in after:
        r.trigger_breached_at = clock.now() if after["Trigger"] == "Breached" else None
    r.modified_by = actor
    r.save()
    summary = "; ".join(f"{k.lower()} {before[k] or '—'} → {after[k] or '—'}" for k in after)
    return record(actor, f"{r.reference} updated — {summary}", r, screen=screen, before=before, after=after)


@transaction.atomic
def review(actor, r, note, screen="risk"):
    _manager(actor)
    if not (note or "").strip():
        raise Refusal("invalid", ["Write what the review found: is the risk still live, and what is being done?"], "Add the review note.",
                      status=422)
    r.reviewed_at, r.review_note, r.modified_by = clock.now(), note.strip(), actor
    r.save()
    return record(actor, f"{r.reference} reviewed — {note.strip()}", r, screen=screen)


@transaction.atomic
def close(actor, r, reason, screen="risk"):
    _manager(actor)
    if not (reason or "").strip():
        raise Refusal("invalid", ["Give the reason for closing it, for example the cause has been removed."], "A reason is needed.", status=422)
    r.is_active, r.closed_reason, r.modified_by = False, reason.strip()[:300], actor
    r.save()
    return record(actor, f"{r.reference} closed — {reason.strip()}", r, screen=screen)


@transaction.atomic
def link(actor, r, enquiry, screen="risk"):
    _manager(actor)
    if r.enquiries.filter(pk=enquiry.pk).exists():
        raise Refusal("already_linked", [f"{enquiry.reference} is already linked to {r.reference}."], "Nothing to change.")
    r.enquiries.add(enquiry)
    return record(actor, f"{r.reference} linked to {enquiry.kind.lower()} {enquiry.reference} ({enquiry.contact.names})", r, screen=screen)


@transaction.atomic
def unlink(actor, r, enquiry, screen="risk"):
    _manager(actor)
    r.enquiries.remove(enquiry)
    return record(actor, f"{r.reference} no longer linked to {enquiry.reference}", r, screen=screen)
