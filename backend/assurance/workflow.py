"""The accreditation workflow.

Held accreditations: each covers a set of courses and expires. Renewing records a new accreditation
that renews the old one (history kept). A renewal is due within ninety days of expiry; once lapsed
without a renewal, delivery of the courses it covers stops: new intakes of them cannot be confirmed.

New scope (or a renewal) runs as a project through ACC_STEPS, each step with a due date. Completing a
step records the date and a note; a step past its due date is overdue and reaches the desk. Completing
the last step, Accredited, records the accreditation the project produced and marks its courses
accredited. Every change is audited."""

import datetime as dt
import hashlib
from pathlib import Path

from django.conf import settings
from django.db import transaction

from assurance.models import ACC_STEPS, Accreditation, AccreditationProject, Document, Library
from audit.services import record
from core import clock
from core.api_support import Refusal
from core.models import Body
from courses.models import Course

CERT_ENTITY = "assurance.accreditation"


def spread(start: dt.date, target: dt.date, n: int = len(ACC_STEPS)) -> list[dt.date]:
    """Due dates for the steps, spread evenly from start to the target (the last step on the target)."""
    days = max((target - start).days, n)
    return [start + dt.timedelta(days=round(days * (i + 1) / n)) for i in range(n)]


# --- reading ------------------------------------------------------------------------------

def current_held():
    """Accreditations in force or lapsed, but not yet renewed: the latest of each line."""
    return Accreditation.objects.filter(is_active=True, renewed_by__isnull=True)


def standing(a: Accreditation, on: dt.date | None = None) -> tuple[str, str]:
    on = on or clock.today()
    days = (a.expires_on - on).days
    if days < 0:
        return f"Lapsed {-days} days ago — delivery stopped", "bad"
    if days <= 90:
        return f"Renewal due in {days} days", "warn"
    return "In order", "ok"


def covering(course, on: dt.date) -> Accreditation | None:
    """The accreditation that covers a course for delivery on a date: the current one with the latest expiry."""
    held = [a for a in current_held().filter(courses=course)]
    return max(held, key=lambda a: a.expires_on) if held else None


def delivery_blockers(block, on: dt.date | None = None) -> list[str]:
    """A course covered by an accreditation that lapses before the intake ends cannot be delivered."""
    on = on or clock.today()
    a = covering(block.course, on)
    if a is None or a.expires_on >= block.end_date:
        return []
    verb = "lapsed" if a.expires_on < on else "lapses"
    return [f"The {a.body.name} accreditation for {block.course.title} ({a.reference}) {verb} on {a.expires_on.isoformat()}, "
            f"before this intake ends. Delivery under that scope stops until it is renewed."]


def step_state(p: AccreditationProject, on: dt.date | None = None) -> tuple[str, str]:
    on = on or clock.today()
    if p.state == "Accredited":
        return "Accredited", "ok"
    if p.state == "Withdrawn":
        return "Withdrawn", "na"
    due = p.step_due[p.step_index] if p.step_index < len(p.step_due) else None
    if due and due < on:
        return f"{ACC_STEPS[p.step_index]} overdue by {(on - due).days} days", "bad"
    if due and (due - on).days <= 14:
        return f"{ACC_STEPS[p.step_index]} due in {(due - on).days} days", "warn"
    return f"{ACC_STEPS[p.step_index]} in progress", "info"


def overdue_projects(on: dt.date | None = None):
    on = on or clock.today()
    return [p for p in AccreditationProject.objects.filter(is_active=True, state="Active").select_related("body", "owner")
            if p.step_index < len(p.step_due) and p.step_due[p.step_index] and p.step_due[p.step_index] < on]


def certificate(a: Accreditation) -> Document | None:
    return Document.objects.filter(is_active=True, entity_type=CERT_ENTITY, entity_ref=a.reference).first()


# --- permissions --------------------------------------------------------------------------

def _manager(actor):
    if not actor.can("assurance", write=True):
        raise Refusal("forbidden", ["Accreditation is managed by the head of department (the training manager)."], "Not permitted.",
                      status=403)


def _manager_or_owner(actor, project):
    if not (actor.can("assurance", write=True) or project.owner_id == actor.pk):
        raise Refusal("forbidden", [f"{project.reference} is run by {project.owner.display_name}; only they or the head of department "
                                    "move it on."], "Not permitted.", status=403)


def _courses(codes):
    found = list(Course.objects.filter(code__in=codes or [], is_active=True))
    missing = sorted(set(codes or []) - {c.code for c in found})
    return found, missing


def _accredit_courses(courses, body):
    for c in courses:
        if not c.is_accredited or c.accreditation_body_id != body.pk:
            c.is_accredited, c.accreditation_body = True, body
            c.save(update_fields=["is_accredited", "accreditation_body"])


# --- held accreditations --------------------------------------------------------------------

@transaction.atomic
def add_held(actor, *, body_code, scope, number, granted_on, expires_on, course_codes, screen="accreditation"):
    """Record an accreditation already held (for example one granted before the hub)."""
    _manager(actor)
    body = Body.objects.filter(code=body_code).first()
    courses, missing = _courses(course_codes)
    reasons = []
    if body is None:
        reasons.append("Choose the accrediting body.")
    if not (scope or "").strip():
        reasons.append("Describe the scope, for example 'Meat examination — red meat, poultry and game'.")
    if expires_on is None:
        reasons.append("Give the expiry date.")
    elif granted_on and expires_on <= granted_on:
        reasons.append("The expiry date must be after the date it was granted.")
    if missing:
        reasons.append(f"Unknown course {', '.join(missing)}.")
    if reasons:
        raise Refusal("invalid", reasons, "The accreditation cannot be recorded yet.", status=422)
    a = Accreditation.objects.create(body=body, scope=scope.strip(), number=(number or "").strip(), granted_on=granted_on,
                                     expires_on=expires_on, created_by=actor, modified_by=actor)
    a.courses.set(courses)
    _accredit_courses(courses, body)
    return a, record(actor, f"{a.reference} {body.name} accreditation recorded — {a.scope}, valid to {expires_on.isoformat()}"
                            + (f"; covers {', '.join(c.code for c in courses)}" if courses else ""), a, screen=screen)


@transaction.atomic
def renew_held(actor, held, *, number, granted_on, expires_on, screen="accreditation"):
    _manager(actor)
    held = Accreditation.objects.select_for_update().get(pk=held.pk)
    if hasattr(held, "renewed_by"):
        raise Refusal("already_renewed", [f"{held.reference} was already renewed by {held.renewed_by.reference}."], "Renew the current one.")
    reasons = []
    if expires_on is None:
        reasons.append("Give the new expiry date.")
    elif expires_on <= held.expires_on:
        reasons.append(f"The new expiry must be after the current one ({held.expires_on.isoformat()}).")
    elif granted_on and expires_on <= granted_on:
        reasons.append("The expiry date must be after the date it was granted.")
    if reasons:
        raise Refusal("invalid", reasons, "The renewal cannot be recorded yet.", status=422)
    new = Accreditation.objects.create(body=held.body, scope=held.scope, number=(number or held.number or "").strip(),
                                       granted_on=granted_on, expires_on=expires_on, renews=held, created_by=actor, modified_by=actor)
    new.courses.set(held.courses.all())
    # A renewal project for this accreditation is finished by the renewal.
    for p in held.renewal_projects.filter(is_active=True, state="Active"):
        _finish(actor, p, new)
    return new, record(actor, f"{held.reference} renewed as {new.reference} — {held.body.name}, {held.scope}, valid to "
                              f"{expires_on.isoformat()} (was {held.expires_on.isoformat()})", new, screen=screen,
                       before={"Expires": held.expires_on.isoformat()}, after={"Expires": expires_on.isoformat()})


@transaction.atomic
def set_courses(actor, held, course_codes, screen="accreditation"):
    _manager(actor)
    courses, missing = _courses(course_codes)
    if missing:
        raise Refusal("invalid", [f"Unknown course {', '.join(missing)}."], "Check the courses.", status=422)
    before = sorted(held.courses.values_list("code", flat=True))
    held.courses.set(courses)
    _accredit_courses(courses, held.body)
    after = sorted(c.code for c in courses)
    if before == after:
        raise Refusal("no_change", ["Nothing was changed."], "There is nothing to save.")
    return record(actor, f"{held.reference} courses covered: {', '.join(before) or 'none'} → {', '.join(after) or 'none'}", held,
                  screen=screen, before={"Courses": before}, after={"Courses": after})


@transaction.atomic
def attach_certificate(actor, held, filename: str, content: bytes, screen="accreditation"):
    from learners.evidence import _sniff

    _manager(actor)
    if not content or len(content) > settings.FSA_UPLOAD_MAX_BYTES:
        raise Refusal("invalid", ["Choose the certificate: a PDF, JPG or PNG up to 5 MB."], "Check the file.", status=422)
    ext = _sniff(content[:8])
    if ext is None:
        raise Refusal("invalid", ["Upload a PDF, or a photo or scan as JPG or PNG."], "That file type is not accepted.", status=422)
    digest = hashlib.sha256(content).hexdigest()
    key = f"agreements/accreditation/{held.reference}-{digest[:12]}.{ext}"
    target = Path(settings.FSA_FILE_ROOT) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    old = certificate(held)
    if old:
        old.is_active, old.state, old.modified_by = False, "Archived", actor
        old.save()
    name = Path(filename or f"certificate.{ext}").name[:120]
    doc = Document.objects.create(library=Library.objects.get(code="agreements"),
                                  title=f"Accreditation certificate — {held.reference} · {name}", entity_type=CERT_ENTITY,
                                  entity_ref=held.reference, storage_key=key, sha256=digest, state="Held", created_by=actor, modified_by=actor)
    return doc, record(actor, f"{held.reference} certificate uploaded — {name} ({doc.reference})", held, screen=screen)


# --- documents on each step of an application --------------------------------------------------

STEP_DOCS = "assurance.application.step"
STEP_DOC_HINT = [  # what each step typically files
    "the scope letter or the list of qualifications applied for",
    "the self-evaluation against the body's criteria",
    "learning material, assessment tools, facilitator registrations and policies",
    "the application as submitted, and the body's acknowledgement",
    "the site visit confirmation, and the visit report",
    "the letter or certificate of accreditation",
]


def step_documents(p) -> dict[int, list]:
    out = {i: [] for i in range(len(ACC_STEPS))}
    for d in (Document.objects.filter(is_active=True, entity_ref=p.reference, entity_type__startswith=STEP_DOCS)
              .order_by("created_at", "id")):
        i = int(d.entity_type[len(STEP_DOCS):])
        out.setdefault(i, []).append(d)
    return out


@transaction.atomic
def attach_step_document(actor, p, index: int, filename: str, content: bytes, screen="accreditation"):
    """File a document against any step: ahead of time (the site visit confirmation arrives early), now, or late."""
    from learners.evidence import _sniff

    _manager_or_owner(actor, p)
    if p.state == "Withdrawn":
        raise Refusal("closed", [f"{p.reference} was withdrawn."], "Nothing to file against.")
    if not 0 <= index < len(ACC_STEPS):
        raise Refusal("invalid", [f"There is no step {index + 1}."], "Check the step.", status=422)
    if not content or len(content) > settings.FSA_UPLOAD_MAX_BYTES:
        raise Refusal("invalid", ["Choose the document: a PDF, JPG or PNG up to 5 MB."], "Check the file.", status=422)
    ext = _sniff(content[:8])
    if ext is None:
        raise Refusal("invalid", ["Upload a PDF, or a photo or scan as JPG or PNG."], "That file type is not accepted.", status=422)
    digest = hashlib.sha256(content).hexdigest()
    key = f"agreements/applications/{p.reference}/step{index + 1}-{digest[:12]}.{ext}"
    target = Path(settings.FSA_FILE_ROOT) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    name = Path(filename or f"document.{ext}").name[:120]
    doc = Document.objects.create(library=Library.objects.get(code="agreements"),
                                  title=f"{p.reference} {ACC_STEPS[index]} · {name}"[:200], entity_type=f"{STEP_DOCS}{index}",
                                  entity_ref=p.reference, storage_key=key, sha256=digest, state="Held", created_by=actor, modified_by=actor)
    return doc, record(actor, f"{p.reference} {ACC_STEPS[index].lower()}: document filed — {name} ({doc.reference})", p, screen=screen)


# --- projects -----------------------------------------------------------------------------

@transaction.atomic
def start_project(actor, *, body_code, scope, owner_ref, target_date, course_codes, renews_ref="", step_due=None,
                  screen="accreditation"):
    from identity.models import Account

    _manager(actor)
    body = Body.objects.filter(code=body_code).first()
    owner = Account.objects.filter(reference=owner_ref, is_active=True).first()
    courses, missing = _courses(course_codes)
    renews = Accreditation.objects.filter(reference=renews_ref, is_active=True).first() if renews_ref else None
    today = clock.today()
    reasons = []
    if body is None:
        reasons.append("Choose the accrediting body.")
    if not (scope or "").strip():
        reasons.append("Describe the scope being sought.")
    if owner is None:
        reasons.append("Choose who runs the application.")
    if target_date is None or target_date <= today:
        reasons.append("Give a target date in the future.")
    if missing:
        reasons.append(f"Unknown course {', '.join(missing)}.")
    if renews_ref and renews is None:
        reasons.append(f"No accreditation {renews_ref}.")
    due = list(step_due or [])
    if due and (len(due) != len(ACC_STEPS) or any(d is None for d in due)):
        reasons.append("Give a due date for every step.")
    elif due and any(b < a for a, b in zip(due, due[1:])):
        reasons.append("Each step's due date must be on or after the step before.")
    if reasons:
        raise Refusal("invalid", reasons, "The application cannot be started yet.", status=422)
    p = AccreditationProject.objects.create(
        body=body, scope=scope.strip(), owner=owner, target_date=target_date, renews=renews,
        step_due=due or spread(today, target_date), step_done=[None] * len(ACC_STEPS), step_notes=[""] * len(ACC_STEPS),
        created_by=actor, modified_by=actor)
    p.courses.set(courses or (renews.courses.all() if renews else []))
    return p, record(actor, f"{p.reference} started — {body.name}, {p.scope}; run by {owner.display_name}, target {target_date.isoformat()}",
                     p, screen=screen)


def _finish(actor, p, accreditation):
    today = clock.today()
    done = list(p.step_done) + [None] * (len(ACC_STEPS) - len(p.step_done))
    for i in range(len(ACC_STEPS)):
        done[i] = done[i] or today
    p.step_done, p.step_index, p.state, p.result, p.modified_by = done, len(ACC_STEPS) - 1, "Accredited", accreditation, actor
    p.save()


@transaction.atomic
def complete_step(actor, p, *, note="", number="", granted_on=None, expires_on=None, screen="accreditation"):
    """Complete the current step. Completing Accredited records the accreditation it produced."""
    p = AccreditationProject.objects.select_for_update(of=("self",)).select_related("owner", "body", "renews").get(pk=p.pk)
    _manager_or_owner(actor, p)
    if p.state != "Active":
        raise Refusal("closed", [f"{p.reference} is {p.state.lower()}."], "Nothing to move on.")
    i = p.step_index
    step = ACC_STEPS[i]
    today = clock.today()
    if not step_documents(p)[i]:
        raise Refusal("document_needed", [f"Attach the document for “{step}”: {STEP_DOC_HINT[i]}."],
                      "A step is completed with its document on file.")
    done = list(p.step_done) + [None] * (len(ACC_STEPS) - len(p.step_done))
    notes = list(p.step_notes) + [""] * (len(ACC_STEPS) - len(p.step_notes))
    if i == len(ACC_STEPS) - 1:  # accreditation granted
        reasons = []
        if expires_on is None or expires_on <= today:
            reasons.append("Give the expiry date of the accreditation granted.")
        if granted_on and expires_on and expires_on <= granted_on:
            reasons.append("The expiry date must be after the date it was granted.")
        if reasons:
            raise Refusal("invalid", reasons, "Record what was granted.", status=422)
        if p.renews and not hasattr(p.renews, "renewed_by"):
            accreditation, _ = renew_held(actor, p.renews, number=number, granted_on=granted_on or today, expires_on=expires_on, screen=screen)
            p.refresh_from_db()
        else:
            accreditation = Accreditation.objects.create(body=p.body, scope=p.scope, number=(number or "").strip(),
                                                         granted_on=granted_on or today, expires_on=expires_on, created_by=actor, modified_by=actor)
            accreditation.courses.set(p.courses.all())
            _accredit_courses(list(p.courses.all()), p.body)
        notes[i] = (note or "").strip()
        p.step_notes = notes
        _finish(actor, p, accreditation)
        if certificate(accreditation) is None:  # the letter filed on the last step is the accreditation's certificate
            letter = step_documents(p)[i][-1]
            Document.objects.create(library=letter.library, title=f"Accreditation certificate — {accreditation.reference} · "
                                    f"{letter.title.rsplit(' · ', 1)[-1]}"[:200], entity_type=CERT_ENTITY,
                                    entity_ref=accreditation.reference, storage_key=letter.storage_key, sha256=letter.sha256,
                                    state="Held", created_by=actor, modified_by=actor)
        return p, record(actor, f"{p.reference} accredited — {p.body.name}, {p.scope}; {accreditation.reference} valid to "
                                f"{accreditation.expires_on.isoformat()}", p, screen=screen)
    done[i], notes[i] = today, (note or "").strip()
    late = p.step_due[i] and today > p.step_due[i]
    p.step_done, p.step_notes, p.step_index, p.modified_by = done, notes, i + 1, actor
    p.save()
    return p, record(actor, f"{p.reference} {step.lower()} complete{' (late)' if late else ''} — next: {ACC_STEPS[i + 1].lower()}, due "
                            f"{p.step_due[i + 1].isoformat() if p.step_due[i + 1] else 'not set'}"
                            + (f"; {note.strip()}" if (note or "").strip() else ""), p, screen=screen)


@transaction.atomic
def replan(actor, p, *, owner_ref=None, target_date=None, step_due=None, screen="accreditation"):
    from identity.models import Account

    _manager(actor)
    if p.state != "Active":
        raise Refusal("closed", [f"{p.reference} is {p.state.lower()}."], "Nothing to change.")
    before = {"Owner": p.owner.display_name, "Target": p.target_date.isoformat(), "Due": [d.isoformat() if d else "" for d in p.step_due]}
    if owner_ref:
        owner = Account.objects.filter(reference=owner_ref, is_active=True).first()
        if owner is None:
            raise Refusal("invalid", ["Choose who runs the application."], "Check the owner.", status=422)
        p.owner = owner
    if target_date:
        p.target_date = target_date
    if step_due is not None:
        if len(step_due) != len(ACC_STEPS) or any(d is None for d in step_due):
            raise Refusal("invalid", ["Give a due date for every step."], "Check the dates.", status=422)
        if any(b < a for a, b in zip(step_due, step_due[1:])):
            raise Refusal("invalid", ["Each step's due date must be on or after the step before."], "Check the dates.", status=422)
        p.step_due = list(step_due)
    after = {"Owner": p.owner.display_name, "Target": p.target_date.isoformat(), "Due": [d.isoformat() if d else "" for d in p.step_due]}
    changed = [k for k in after if after[k] != before[k]]
    if not changed:
        raise Refusal("no_change", ["Nothing was changed."], "There is nothing to save.")
    p.modified_by = actor
    p.save()
    text = "; ".join("step due dates changed" if k == "Due" else f"{k.lower()} {before[k]} → {after[k]}" for k in changed)
    return p, record(actor, f"{p.reference} re-planned — {text}", p, screen=screen, before={k: before[k] for k in changed},
                     after={k: after[k] for k in changed})


@transaction.atomic
def withdraw(actor, p, reason, screen="accreditation"):
    _manager(actor)
    if p.state != "Active":
        raise Refusal("closed", [f"{p.reference} is {p.state.lower()}."], "Nothing to withdraw.")
    if not (reason or "").strip():
        raise Refusal("reason_needed", ["Give the reason for withdrawing the application."], "A reason is needed.", status=422)
    p.state, p.modified_by = "Withdrawn", actor
    p.notes = (p.notes + "\n" if p.notes else "") + f"Withdrawn {clock.today().isoformat()}: {reason.strip()}"
    p.save()
    return record(actor, f"{p.reference} withdrawn — {reason.strip()}", p, screen=screen)
