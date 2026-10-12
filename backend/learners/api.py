from django.db.models import Count, Q
from ninja import Router, Schema

from core import clock, pii
from core.api_support import Refusal, iso, ok, require, stamp
from learners import services
from learners.models import ENR_STAGES, Certificate, Enrolment, Result
from learners.rules import advance_blockers, certificate_blockers, gate_blockers

router = Router(tags=["learners"])


def _screen(request, default):
    return request.headers.get("X-FSA-Screen", default)


def enrolment_dict(e: Enrolment):
    return {
        "ref": e.reference, "learner": e.learner.names, "learnerRef": e.learner.reference,
        "course": e.course.title, "gated": e.course.entry_gate == "PrerequisiteAndGrade10",
        "intake": iso(e.plan_block.start_date) if e.plan_block_id else None,
        "stageIndex": e.stage_index, "stage": e.stage,
        "prerequisiteResult": float(e.prerequisite_result) if e.prerequisite_result is not None else None,
        "grade10": e.grade10_evidence_held,
        "basis": {"PerLearner": "Per learner", "PerGroup": "Per group", "UniversityAgreement": "University agreement",
                  "Employee": "Employee"}[e.basis],
        "gateBlockedBy": gate_blockers(e) if e.stage_index == 0 else [],
        "advanceBlockedBy": advance_blockers(e),
        "owner": e.assigned_to.display_name if e.assigned_to_id else None,
    }


def _enrolments():
    return Enrolment.objects.filter(is_active=True).select_related("learner", "course__prior_course", "plan_block", "assigned_to")


@router.get("/enrolments")
def enrolments(request):
    require(request, "learners")
    rows = [enrolment_dict(e) for e in _enrolments()]
    return ok({"stages": ENR_STAGES, "items": rows,
               "counts": [sum(1 for r in rows if r["stageIndex"] == i) for i in range(5)]},
              source="Enrolment register")


@router.patch("/enrolments/{ref}/stage")
def advance(request, ref: str):
    require(request, "learners", write=True)
    e = _enrolments().filter(reference=ref).first()
    if not e:
        raise Refusal("not_found", [f"No enrolment {ref}."], "Not found.", status=404)
    audit = services.advance_enrolment(request.user, e, screen=_screen(request, "enrolments"))
    return ok(enrolment_dict(e), audit=audit)


class GateUpdate(Schema):
    prerequisiteResult: float | None = None
    grade10EvidenceHeld: bool | None = None


@router.patch("/enrolments/{ref}/gate")
def gate(request, ref: str, body: GateUpdate):
    require(request, "learners", write=True)
    e = _enrolments().filter(reference=ref).first()
    if not e:
        raise Refusal("not_found", [f"No enrolment {ref}."], "Not found.", status=404)
    if body.prerequisiteResult is not None and not 0 <= body.prerequisiteResult <= 100:
        raise Refusal("invalid", ["A test result is a percentage from 0 to 100."], "Check the result.", status=422)
    audit = services.update_gate(request.user, e, body.prerequisiteResult, body.grade10EvidenceHeld,
                                 screen=_screen(request, "enrolments"))
    return ok(enrolment_dict(e), audit=audit)


def result_dict(r: Result):
    m = getattr(r, "moderation", None)
    cert = getattr(m, "certificate", None) if m else None
    if cert:
        position, tone = f"Issued {cert.reference}", "ok"
    elif m and m.outcome == "Competent":
        position, tone = "Moderated — awaiting certificate", "info"
    elif m:
        position, tone = "Moderated — remediation", "warn"
    else:
        position, tone = "Awaiting moderation", "warn"
    return {
        "ref": r.reference, "learner": r.enrolment.learner.names, "learnerRef": r.enrolment.learner.reference,
        "course": r.enrolment.course.title, "session": r.session.reference if r.session_id else None,
        "assessor": r.assessed_by.display_name, "mark": float(r.mark), "outcome": r.outcome,
        "moderated": m is not None, "moderatedOutcome": m.outcome if m else None,
        "moderatedBy": m.moderated_by.display_name if m else None,
        "certificate": cert.reference if cert else None,
        "position": position, "tone": tone,
        "certificateBlockedBy": certificate_blockers(r),
        "remediation": r.remediation_plan,
    }


def _results():
    return Result.objects.filter(is_active=True).select_related(
        "enrolment__learner", "enrolment__course", "session", "assessed_by",
        "moderation__moderated_by", "moderation__certificate")


def _scoped_results(request):
    qs = _results()
    if request.user.scope("results") == "own":
        qs = qs.filter(session__plan_block__facilitator=request.user) | qs.filter(assessed_by=request.user)
    return qs


@router.get("/results")
def results(request):
    require(request, "results")
    rows = [result_dict(r) for r in _scoped_results(request)]
    return ok({"items": rows, "canModerate": request.user.can("moderation", write=True)},
              source="Assessment results · moderation records")


class Moderate(Schema):
    outcome: str | None = None
    notes: str = ""


@router.post("/results/{ref}/moderate")
def moderate(request, ref: str, body: Moderate):
    require(request, "moderation", write=True, message="Moderation is recorded by the training manager or a moderator.")
    r = _results().filter(reference=ref).first()
    if not r:
        raise Refusal("not_found", [f"No result {ref}."], "Not found.", status=404)
    if body.outcome not in (None, "Competent", "NotYetCompetent"):
        raise Refusal("invalid", ["The outcome is Competent or NotYetCompetent."], "Check the outcome.", status=422)
    audit = services.moderate(request.user, r, body.outcome, body.notes, screen=_screen(request, "results"))
    r = _results().get(pk=r.pk)
    return ok(result_dict(r), audit=audit)


def certificate_dict(c: Certificate):
    r = c.moderation.result
    return {
        "ref": c.reference, "result": r.reference, "learner": r.enrolment.learner.names,
        "course": r.enrolment.course.title, "mark": float(r.mark),
        "issuedAt": stamp(c.issued_at, "%Y-%m-%d"), "issuedBy": c.issued_by.display_name,
        "verificationCode": c.verification_code,
        "depositoryRef": c.document.reference if c.document_id else None,
        "revoked": c.revoked_at is not None,
    }


@router.get("/certificates")
def certificates(request):
    require(request, "certification")
    issued = [certificate_dict(c) for c in Certificate.objects.select_related(
        "moderation__result__enrolment__learner", "moderation__result__enrolment__course", "issued_by", "document")]
    pending = [result_dict(r) for r in _results().filter(moderation__certificate__isnull=True)]
    return ok({"issued": issued, "candidates": pending, "canIssue": request.user.can("certification", write=True)},
              source="Certification register · moderation records")


class Issue(Schema):
    resultRef: str


@router.post("/certificates")
def issue(request, body: Issue):
    require(request, "certification", write=True, message="Certificates are signed and issued by the training manager.")
    r = _results().filter(reference=body.resultRef).first()
    if not r:
        raise Refusal("not_found", [f"No result {body.resultRef}."], "Not found.", status=404)
    cert, audit = services.issue_certificate(request.user, r, screen=_screen(request, "certificates"))
    cert = Certificate.objects.select_related("moderation__result__enrolment__learner", "moderation__result__enrolment__course",
                                              "issued_by", "document").get(pk=cert.pk)
    return ok(certificate_dict(cert), audit=audit)


@router.get("/learners")
def learners(request):
    require(request, "learners")
    from learners.models import Learner

    rows = [{
        "ref": l.reference, "name": l.names, "type": l.learner_type,
        "organisation": l.organisation.name if l.organisation_id else "",
        "hrLinked": l.hr_person_id is not None,
        "idNumber": pii.mask(l.id_type, l.id_last4) or "Not captured",
        "studentNumber": l.external_ref,
        "enrolments": [f"{e.reference} · {e.course.title} · {e.stage}" for e in l.enrolments.all()],
    } for l in Learner.objects.filter(is_active=True).select_related("organisation").prefetch_related("enrolments__course")]
    return ok(rows, source="Learner directory · HR directory link")


# --- registration: how a learner becomes part of the system --------------------------------

@router.get("/intakes")
def intakes(request, course: str | None = None):
    """Intakes that can take registrations: current or future, not cancelled, with their free seats."""
    from delivery.models import PlanBlock

    require(request, "learners")
    today = clock.today()
    qs = (PlanBlock.objects.filter(is_active=True, end_date__gte=today).exclude(state="Cancelled")
          .select_related("course", "venue", "facilitator").order_by("start_date")
          .annotate(booked=Count("enrolments", filter=Q(enrolments__is_active=True))))
    if course:
        qs = qs.filter(course__code=course)
    return ok([{
        "ref": b.reference, "courseCode": b.course.code, "course": b.course.title, "gated": b.course.entry_gate == "PrerequisiteAndGrade10",
        "start": iso(b.start_date), "end": iso(b.end_date), "venue": b.venue.name, "facilitator": b.facilitator.display_name,
        "seats": b.seats_booked, "capacity": b.capacity, "free": b.capacity - b.seats_booked, "state": b.state,
        "cadence": b.intake_cadence,
    } for b in qs])


class Registration(Schema):
    blockRef: str
    consent: bool = False
    enquiryRef: str = ""
    learnerRef: str = ""
    names: str = ""
    email: str = ""
    phone: str = ""
    learnerType: str = "Public"
    organisation: str = ""
    idType: str = "SAID"
    idNumber: str = ""
    prerequisiteResult: float | None = None
    grade10EvidenceHeld: bool = False


@router.post("/enrolments")
def register(request, body: Registration):
    """Register a learner onto an intake: a new person or an existing learner, optionally from an enquiry."""
    from learners.registration import Person, register_individual

    require(request, "learners", write=True, message="Learners are registered by the enquiry handler or training manager.")
    enrolment, audit = register_individual(
        request.user, Person(body.names, body.email, body.phone, id_number=body.idNumber, id_type=body.idType), body.learnerType, body.organisation, body.blockRef,
        body.consent, enquiry_ref=body.enquiryRef, learner_ref=body.learnerRef,
        prerequisite_result=body.prerequisiteResult, grade10_evidence_held=body.grade10EvidenceHeld,
        screen=_screen(request, "enrolments"))
    enrolment = _enrolments().get(pk=enrolment.pk)
    return ok(enrolment_dict(enrolment), audit=audit)


class Student(Schema):
    names: str
    studentNumber: str = ""
    email: str = ""
    phone: str = ""
    idNumber: str = ""
    idType: str = "SAID"


class Cohort(Schema):
    organisationRef: str
    blockRef: str
    students: list[Student]
    consent: bool = False


@router.post("/partnerships/cohort")
def import_cohort(request, body: Cohort):
    """A university's student list for a placement intake."""
    from learners.registration import Person, import_cohort as run_import

    require(request, "learners", write=True, message="Cohort lists are imported by the training administrator or training manager.")
    enrolments, skipped, placement, audit = run_import(
        request.user, body.organisationRef, body.blockRef,
        [Person(s.names, s.email, s.phone, s.studentNumber, s.idNumber, s.idType) for s in body.students], body.consent,
        screen=_screen(request, "partnerships"))
    return ok({"imported": len(enrolments), "skipped": skipped, "placement": placement.reference,
               "enrolments": [e.reference for e in enrolments]}, audit=audit)


@router.get("/universities")
def universities(request):
    from demand.models import Organisation

    require(request, "learners")
    return ok([{"ref": o.reference, "name": o.name}
               for o in Organisation.objects.filter(is_active=True, relationship="University").order_by("name")])
