"""Adding and editing courses. Every change is audited with its old and new values; the requirement
history is append-only, and a requirement change never reaches an intake that already has learners."""

import datetime as dt
import re
from decimal import Decimal

from django.db import transaction

from audit.services import record
from core import clock
from core.api_support import Refusal
from core.models import Body, Service, Stream
from courses import requirements
from courses.models import ENTRY_GATES, Course, CourseRequirement

KINDS = dict(ENTRY_GATES)
CODE = re.compile(r"^TRN-[A-Z0-9]{2,12}$")


def _requirement_problems(kind, pass_mark, prior_code, description, course=None):
    reasons, prior = [], None
    if kind not in KINDS:
        return ["Choose the kind of entry requirement."], None
    if kind == "PrerequisiteAndGrade10":
        if pass_mark is None or not 0 < pass_mark <= 100:
            reasons.append("Give the pass mark for the prerequisite test, a percentage from 1 to 100.")
    if kind == "PriorCourse":
        prior = Course.objects.filter(code=prior_code, is_active=True).first()
        if prior is None:
            reasons.append("Choose the course the learner must have passed first.")
        elif course is not None and prior.pk == course.pk:
            reasons.append("A course cannot require itself.")
    if kind == "Documented" and not (description or "").strip():
        reasons.append("Describe the document or experience required, for example 'Two years industry experience'.")
    return reasons, prior


def _details(service, stream, days, mode, body):
    reasons = []
    svc = Service.objects.filter(code=service).first()
    st = Stream.objects.filter(code=stream).first()
    bd = Body.objects.filter(code=body).first() if body else None
    if svc is None:
        reasons.append("Choose the FSA service the course supports.")
    if st is None:
        reasons.append("Choose the planner stream.")
    if days is None or not 1 <= days <= 365:
        reasons.append("Give the duration in days, from 1 to 365.")
    if not (mode or "").strip():
        reasons.append("Describe the delivery, for example 'Contact' or 'Contact and workplace'.")
    if body and bd is None:
        reasons.append("Choose the accrediting body from the list.")
    return reasons, svc, st, bd


@transaction.atomic
def create_course(actor, *, code, title, service, stream, days, mode, body, kind, pass_mark, prior_code, description,
                  screen="catalogue"):
    code = (code or "").strip().upper()
    reasons = []
    if not CODE.match(code):
        reasons.append("A course code is TRN- followed by 2 to 12 capital letters or digits, for example TRN-PME3.")
    elif Course.objects.filter(code=code).exists():
        reasons.append(f"{code} is already in the catalogue. A course code is used once and never reused.")
    if not (title or "").strip():
        reasons.append("Give the course title.")
    more, svc, st, bd = _details(service, stream, days, mode, body)
    req_reasons, prior = _requirement_problems(kind, pass_mark, prior_code, description)
    reasons += more + req_reasons
    if reasons:
        raise Refusal("invalid", reasons, "The course cannot be added yet.", status=422)
    course = Course.objects.create(
        code=code, title=title.strip(), service=svc, stream=st, pack_type="", duration_days=days, delivery_mode=mode.strip(),
        entry_gate=kind, entry_requirement="", prior_course=prior, is_accredited=bd is not None, accreditation_body=bd,
        created_by=actor, modified_by=actor,
    )
    req = CourseRequirement.objects.create(
        course=course, version=1, effective_from=clock.today(), kind=kind,
        pass_mark=Decimal(str(pass_mark)) if kind == "PrerequisiteAndGrade10" else None, prior_course=prior,
        description=(description or "").strip() if kind == "Documented" else "", reason="Course added to the catalogue",
        created_by=actor,
    )
    course.entry_requirement = req.label[:160]
    course.save(update_fields=["entry_requirement"])
    audit = record(actor, f"{code} {course.title} added to the catalogue — entry requirement: {req.label}", course,
                   screen=screen, after={"Title": course.title, "Service": svc.name, "Stream": st.name, "Duration": f"{days} days",
                                         "Delivery": course.delivery_mode, "Accreditation": bd.name if bd else "None",
                                         "Entry requirement": req.label})
    return course, audit


@transaction.atomic
def update_course(actor, course, *, title, service, stream, days, mode, body, screen="catalogue"):
    """The course's description: title, service, stream, duration, delivery, accreditation. The code
    never changes, and the entry requirement changes only through a new requirement version."""
    course = Course.objects.select_for_update().get(pk=course.pk)
    reasons = [] if (title or "").strip() else ["Give the course title."]
    more, svc, st, bd = _details(service, stream, days, mode, body)
    reasons += more
    if reasons:
        raise Refusal("invalid", reasons, "The course cannot be saved.", status=422)

    def view(c):
        return {"Title": c.title, "Service": c.service.name, "Stream": c.stream.name, "Duration": f"{c.duration_days} days",
                "Delivery": c.delivery_mode, "Accreditation": c.accreditation_body.name if c.accreditation_body_id else "None"}

    before = view(course)
    course.title, course.service, course.stream = title.strip(), svc, st
    course.duration_days, course.delivery_mode = days, mode.strip()
    course.accreditation_body, course.is_accredited = bd, bd is not None
    after = view(course)
    changed = {k: after[k] for k in after if after[k] != before[k]}
    if not changed:
        raise Refusal("nothing_to_change", ["Nothing was changed."], "No change.")
    course.modified_by = actor
    course.row_version += 1
    course.save()
    summary = "; ".join(f"{k.lower()} {before[k]} → {after[k]}" for k in changed)
    return course, record(actor, f"{course.code} course details edited — {summary}", course, screen=screen,
                          before={k: before[k] for k in changed}, after=changed)


@transaction.atomic
def change_requirement(actor, course, *, kind, pass_mark, prior_code, description, effective_from: dt.date, reason,
                       screen="catalogue"):
    """A new requirement version. It takes effect from a date after the start of every intake that
    already has learners, so registered learners keep the requirement they registered under."""
    course = Course.objects.select_for_update().get(pk=course.pk)
    reasons, prior = _requirement_problems(kind, pass_mark, prior_code, description, course)
    if not (reason or "").strip():
        reasons.append("Give the reason for the change, for example the regulation or decision that requires it.")
    earliest = requirements.earliest_change(course)
    if effective_from < clock.today():
        reasons.append("A requirement cannot change in the past. Choose today or a later date.")
    elif effective_from < earliest:
        locked = [b for b in requirements.locked_intakes(course) if b.start_date >= effective_from]
        reasons.append(
            "Learners are already registered on " + ", ".join(f"{b.reference} (starts {b.start_date.isoformat()})" for b in locked)
            + f" under the current requirement, which stays for them. The change can take effect from {earliest.isoformat()}, "
              "the next intake without learners.")
    if reasons:
        raise Refusal("invalid", reasons, "The entry requirement cannot be changed yet.", status=422)

    book = requirements.Book()
    previous = book.on(course.pk, effective_from)
    version = (CourseRequirement.objects.filter(course=course).order_by("-version").values_list("version", flat=True).first() or 0) + 1
    req = CourseRequirement(
        course=course, version=version, effective_from=effective_from, kind=kind,
        pass_mark=Decimal(str(pass_mark)) if kind == "PrerequisiteAndGrade10" else None, prior_course=prior,
        description=(description or "").strip() if kind == "Documented" else "", reason=reason.strip(), created_by=actor,
    )
    if previous is not None and req.label == previous.label and req.kind == previous.kind:
        raise Refusal("nothing_to_change", [f"The requirement from {effective_from.isoformat()} is already {req.label}."], "No change.")
    req.save()
    if effective_from <= clock.today():
        course.entry_gate, course.entry_requirement, course.prior_course = kind, req.label[:160], prior
        course.modified_by = actor
        course.save()
    old = previous.label if previous else "None"
    return req, record(actor, f"{course.code} entry requirement version {version}: {old} → {req.label}, "
                              f"from {effective_from.isoformat()} — {req.reason}", course, screen=screen,
                       before={"Entry requirement": old, "Version": previous.version if previous else None},
                       after={"Entry requirement": req.label, "Version": version, "From": effective_from.isoformat(),
                              "Reason": req.reason})
