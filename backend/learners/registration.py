"""How a learner becomes part of the system. Three routes, one engine:

  1. an individual, registered from an enquiry (the enquiry moves to Registered in the same step);
  2. a corporate group, as the delegate list on a per-group quotation;
  3. a university cohort, imported from the university's student list.

Every route: consent recorded, a free seat on the chosen intake, no second enrolment on the same
intake, the seat booked on the plan, one audit entry for the whole registration. A new enrolment
starts at Applied, except university students, whose placement agreement is the entry requirement.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from audit.services import record
from core import clock
from core.api_support import Refusal
from delivery.models import PlanBlock
from core import pii
from demand.models import Enquiry, Organisation, Quotation
from learners.models import Enrolment, Learner
from oversight.models import Rotation

LEARNER_TYPES = ("Public", "Corporate", "University", "Employee")


@dataclass
class Person:
    names: str
    email: str = ""
    phone: str = ""
    external_ref: str = ""
    id_number: str = ""
    id_type: str = "SAID"
    identity: pii.IdentityNumber | None = None  # set by _check_people once validated


def _clean(people: list[Person]) -> list[Person]:
    return [Person(p.names.strip(), p.email.strip(), p.phone.strip(), p.external_ref.strip(), p.id_number.strip(),
                   p.id_type or "SAID") for p in people]


def _check_people(people: list[Person], need_number: bool = False, need_id: bool = False) -> list[str]:
    """Validate every row and name each problem. Identity numbers are parsed here and kept on the row."""
    reasons = []
    for i, p in enumerate(people, start=1):
        who = f"Row {i} ({p.names})" if p.names else f"Row {i}"
        if not p.names:
            reasons.append(f"Row {i}: the learner's name is missing.")
        if need_number and not p.external_ref:
            reasons.append(f"{who}: the student number is missing.")
        if p.email and "@" not in p.email:
            reasons.append(f"{who}: {p.email} is not an email address.")
        p.identity, problem = pii.parse(p.id_type, p.id_number)
        if problem:
            reasons.append(f"{who}: the ID number is not valid — {problem}.")
        elif need_id and p.identity is None:
            reasons.append(f"{who}: the SA ID or passport number is missing. It is how the Academy tells two people "
                           "of the same name apart.")
    seen = {}
    for i, p in enumerate(people, start=1):
        # The same person twice in one list: by ID number first, then student number, then name.
        key = (f"id:{p.identity.id_type}:{p.identity.number}" if p.identity
               else f"no:{p.external_ref.lower()}" if p.external_ref else f"name:{p.names.lower()}")
        if p.names and key in seen:
            reasons.append(f"Row {i} repeats row {seen[key]} ({p.names}).")
        seen.setdefault(key, i)
    return reasons


def _intake(block_ref: str, course=None) -> PlanBlock:
    """The intake, locked for update so two registrations cannot take the same last seat."""
    block = (PlanBlock.objects.select_for_update(of=("self",)).select_related("course", "venue", "facilitator")
             .filter(reference=block_ref, is_active=True).first())
    if block is None:
        raise Refusal("no_intake", [f"There is no intake {block_ref} on the training plan."], "Choose an intake from the plan.")
    reasons = []
    if block.state == "Cancelled":
        reasons.append(f"{block.reference} has been cancelled.")
    if course is not None and block.course_id != course.id:
        reasons.append(f"{block.reference} is an intake for {block.course.title}, not {course.title}.")
    if block.end_date < clock.today():
        reasons.append(f"{block.reference} ended on {block.end_date.isoformat()}. Choose a current or future intake.")
    if reasons:
        raise Refusal("intake_unavailable", reasons, "This intake cannot take registrations.")
    return block


def _check_seats(block: PlanBlock, n: int):
    """Seats booked is the count of active enrolments, read while the intake row is locked (see
    _intake), so two registrations cannot both take the last seat. Nothing is stored to drift."""
    free = block.capacity - block.enrolments.filter(is_active=True).count()
    if n > free:
        raise Refusal("intake_full", [
            f"{block.reference} has {free} of {block.capacity} seats free; this registration needs {n}."
            + (" Raise the block's capacity on the plan or choose another intake." if free else " It is full.")
        ], "There are not enough seats on this intake.")


def _not_already_on(learners: list[Learner], block: PlanBlock):
    taken = set(Enrolment.objects.filter(plan_block=block, is_active=True, learner__in=[l for l in learners if l.pk])
                .values_list("learner__names", flat=True))
    if taken:
        raise Refusal("already_enrolled", [f"{n} is already enrolled on {block.reference}." for n in sorted(taken)],
                      "A learner is enrolled once per intake.")


def _consent(given: bool, who: str):
    if not given:
        raise Refusal("consent_required", [f"Record that {who} consented to the Academy keeping their personal "
                                           "information (POPIA) before registering."], "Consent is required.")


def _find_or_new(person: Person, learner_type: str, organisation, actor) -> Learner:
    """One person, one learner record. Matched on the ID number's keyed hash first (the same person
    whichever client or university sends them), then on the university's student number."""
    existing = None
    index = pii.blind_index(person.identity) if person.identity else None
    if index is not None:
        existing = Learner.objects.filter(id_number_hmac=index).first()
    if existing is None and person.external_ref and organisation is not None:
        existing = Learner.objects.filter(organisation=organisation, external_ref__iexact=person.external_ref).first()
        if existing is not None and index is not None and not existing.id_number_hmac:
            _attach_identity(existing, person.identity, index)
            existing.save()
    if existing is None and index is not None and organisation is not None:
        # A record captured before ID numbers were recorded: same name, same organisation, no ID on
        # file. Exactly one such record is the same person; give it the ID rather than a twin.
        legacy = list(Learner.objects.filter(organisation=organisation, names__iexact=person.names,
                                             id_number_hmac__isnull=True, is_active=True)[:2])
        if len(legacy) == 1:
            existing = legacy[0]
            _attach_identity(existing, person.identity, index)
            existing.save()
    if existing is not None:
        existing.matched = True
        return existing
    learner = Learner(names=person.names, email=person.email, phone=person.phone, external_ref=person.external_ref,
                      learner_type=learner_type, organisation=organisation, consent_at=clock.now(), created_by=actor)
    if person.identity:
        _attach_identity(learner, person.identity, index)
    learner.matched = False
    return learner


def _attach_identity(learner: Learner, identity: pii.IdentityNumber, index: bytes):
    learner.id_type = identity.id_type
    learner.id_number_cipher = pii.encrypt(identity.number)
    learner.id_number_hmac = index
    learner.id_last4 = identity.last4


def _matched_note(learners: list[Learner]) -> str:
    matched = [l for l in learners if getattr(l, "matched", False)]
    if not matched:
        return ""
    return "; matched existing " + ", ".join(f"{l.reference} ({l.names})" for l in matched)


def _enrol(actor, learner: Learner, block: PlanBlock, basis: str, stage: int = 0, **extra) -> Enrolment:
    if not learner.pk:
        learner.save()
    return Enrolment.objects.create(
        learner=learner, course=block.course, plan_block=block, basis=basis, stage_index=stage,
        assigned_to=Rotation.on_duty("LearnerRecords", clock.today()), created_by=actor, **extra,
    )


# --- route 1: an individual, from an enquiry (or directly) ----------------------------------

@transaction.atomic
def register_individual(actor, person: Person, learner_type: str, organisation_name: str, block_ref: str,
                        consent: bool, enquiry_ref: str = "", learner_ref: str = "",
                        prerequisite_result=None, grade10_evidence_held: bool = False, screen="enrolments"):
    enquiry = None
    if enquiry_ref:
        enquiry = Enquiry.objects.select_for_update(of=("self",)).select_related("contact__organisation").filter(reference=enquiry_ref).first()
        if enquiry is None:
            raise Refusal("not_found", [f"No enquiry {enquiry_ref}."], "Not found.", status=404)
        if enquiry.kind != "Enquiry":
            raise Refusal("not_an_enquiry", [f"{enquiry.reference} is a {enquiry.kind.lower()}, not a course enquiry."],
                          "Only a course enquiry registers a learner.")
        if enquiry.enrolments.exists():
            raise Refusal("already_registered", [f"{enquiry.reference} already registered "
                                                 f"{enquiry.enrolments.first().learner.names}."], "Nothing to register.")
    if learner_ref:
        learner = Learner.objects.filter(reference=learner_ref, is_active=True).first()
        if learner is None:
            raise Refusal("not_found", [f"No learner {learner_ref}."], "Not found.", status=404)
    else:
        person = _clean([person])[0]
        reasons = _check_people([person], need_id=learner_type != "University")
        if learner_type not in LEARNER_TYPES:
            reasons.append("Choose the learner type: public, corporate, university or employee.")
        if learner_type == "Corporate" and not organisation_name.strip():
            reasons.append("Name the client organisation for a corporate delegate.")
        if reasons:
            raise Refusal("invalid", reasons, "The learner's details are incomplete.", status=422)
        _consent(consent, person.names)
        org = None
        if organisation_name.strip():
            org = (Organisation.objects.filter(name__iexact=organisation_name.strip()).first()
                   or Organisation.objects.create(name=organisation_name.strip(), created_by=actor))
        learner = _find_or_new(person, learner_type, org, actor)
    if prerequisite_result is not None and not 0 <= prerequisite_result <= 100:
        raise Refusal("invalid", ["A prerequisite result is a percentage from 0 to 100."], "Check the result.", status=422)

    block = _intake(block_ref)
    _not_already_on([learner], block)
    _check_seats(block, 1)
    basis = "PerGroup" if learner.learner_type == "Corporate" else (
        "UniversityAgreement" if learner.learner_type == "University" else (
            "Employee" if learner.learner_type == "Employee" else "PerLearner"))
    enrolment = _enrol(actor, learner, block, basis, enquiry=enquiry,
                       prerequisite_result=Decimal(str(prerequisite_result)) if prerequisite_result is not None else None,
                       grade10_evidence_held=grade10_evidence_held)
    what = (f"{enrolment.reference} opened for {learner.names} ({learner.reference}) on {block.reference} — {block.course.title}"
            + (" — existing learner matched on ID number" if getattr(learner, "matched", False) else ""))
    if enquiry:
        before = enquiry.stage
        now = clock.now()
        enquiry.stage_index = 3
        enquiry.first_response_at = enquiry.first_response_at or now
        enquiry.resolved_at = enquiry.resolved_at or now
        enquiry.modified_by = actor
        enquiry.save()
        what += f"; {enquiry.reference} moved from {before} to Registered"
    audit = record(actor, what, enrolment, screen=screen)
    return enrolment, audit


# --- route 2: a corporate group, from a per-group quotation ----------------------------------

@transaction.atomic
def register_delegates(actor, quotation_ref: str, block_ref: str, people: list[Person], consent: bool, screen="quotes"):
    quotation = (Quotation.objects.select_for_update(of=("self",)).select_related("organisation", "course", "contact")
                 .filter(reference=quotation_ref, is_active=True).first())
    if quotation is None:
        raise Refusal("not_found", [f"No quotation {quotation_ref}."], "Not found.", status=404)
    reasons = []
    if quotation.basis != "PerGroup":
        reasons.append(f"{quotation.reference} is quoted per learner. Register each learner from their enquiry.")
    if quotation.state not in ("Issued", "Accepted"):
        reasons.append(f"{quotation.reference} is {quotation.state.lower()}; delegates are added to an issued or accepted quotation.")
    if quotation.organisation_id is None:
        reasons.append(f"{quotation.reference} has no client organisation to register delegates for.")
    people = _clean(people)
    if not people:
        reasons.append("Add at least one delegate.")
    reasons += _check_people(people, need_id=True)
    already = quotation.enrolments.filter(is_active=True).count()
    if already + len(people) > quotation.learner_count:
        reasons.append(f"{quotation.reference} was quoted for {quotation.learner_count} learners; {already} are already "
                       f"registered, so {quotation.learner_count - already} more can be added, not {len(people)}.")
    if reasons:
        raise Refusal("invalid", reasons, "The delegate list cannot be registered.", status=422)
    _consent(consent, f"{quotation.organisation.name} (for each delegate)")

    block = _intake(block_ref, quotation.course)
    learners = [_find_or_new(p, "Corporate", quotation.organisation, actor) for p in people]
    _not_already_on(learners, block)
    _check_seats(block, len(learners))
    enrolments = [_enrol(actor, l, block, "PerGroup", quotation=quotation) for l in learners]
    before = quotation.state
    if quotation.state == "Issued":
        quotation.state = "Accepted"
        quotation.modified_by = actor
        quotation.save()
    audit = record(actor, f"{len(enrolments)} {'delegate' if len(enrolments) == 1 else 'delegates'} of "
                          f"{quotation.organisation.name} registered on {block.reference} against {quotation.reference}"
                          + (" — quotation accepted" if before == "Issued" else "") + _matched_note(learners),
                   quotation, screen=screen, after={"enrolments": [e.reference for e in enrolments]})
    return enrolments, audit


# --- route 3: a university cohort list --------------------------------------------------------

@transaction.atomic
def import_cohort(actor, organisation_ref: str, block_ref: str, people: list[Person], consent: bool, screen="partnerships"):
    from assurance.models import Placement

    university = Organisation.objects.filter(reference=organisation_ref, is_active=True).first()
    if university is None or university.relationship != "University":
        raise Refusal("not_a_university", [f"{organisation_ref} is not a university partner."], "Choose a university.", status=422)
    people = _clean(people)
    reasons = [] if people else ["The list is empty."]
    reasons += _check_people(people, need_number=True)
    if reasons:
        raise Refusal("invalid", reasons, "The cohort list cannot be imported.", status=422)
    _consent(consent, f"{university.name} (for each student, under the placement agreement)")

    block = _intake(block_ref)
    learners = [_find_or_new(p, "University", university, actor) for p in people]
    on_block = set(Enrolment.objects.filter(plan_block=block, is_active=True, learner__in=[l for l in learners if l.pk])
                   .values_list("learner_id", flat=True))
    new = [l for l in learners if l.pk not in on_block]
    skipped = len(learners) - len(new)
    if not new:
        raise Refusal("already_enrolled", [f"Every student on this list is already enrolled on {block.reference}."],
                      "Nothing to import.")
    _check_seats(block, len(new))
    # The placement agreement is the entry requirement, so students start at Registered.
    enrolments = [_enrol(actor, l, block, "UniversityAgreement", stage=2) for l in new]
    placement = Placement.objects.filter(organisation=university, plan_block=block, is_active=True).first()
    if placement is None:
        placement = Placement.objects.create(
            organisation=university, plan_block=block, cohort_label=f"{university.name} — {block.start_date:%B %Y}",
            cohort_size=len(new), period_start=block.start_date, period_end=block.end_date, created_by=actor)
    else:
        placement.cohort_size = Enrolment.objects.filter(plan_block=block, is_active=True, learner__organisation=university).count()
        placement.save()
    audit = record(actor, f"{len(new)} {university.name} students imported onto {block.reference} ({placement.reference})"
                          + (f"; {skipped} already enrolled and skipped" if skipped else ""),
                   placement, screen=screen, after={"enrolments": [e.reference for e in enrolments]})
    return enrolments, skipped, placement, audit
