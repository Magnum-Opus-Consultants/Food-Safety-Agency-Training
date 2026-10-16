import datetime as dt

from django.conf import settings
from django.db.models import Count, Q
from django.http import FileResponse
from ninja import File, Router, Schema
from ninja.files import UploadedFile

from core import clock, pii
from core.api_support import Refusal, iso, ok, require, stamp
from courses import requirements
from learners import assessment, evidence, services
from learners.models import ENR_STAGES, Certificate, Enrolment, Result
from learners.rules import advance_blockers, certificate_blockers, gate_blockers

router = Router(tags=["learners"])


def _screen(request, default):
    return request.headers.get("X-FSA-Screen", default)


def requirement_dict(req):
    """What an intake (or enrolment) is judged by: the requirement version in force on its start date."""
    if req is None:
        return {"gated": False, "passMark": None, "requirement": "None", "requirementVersion": None}
    return {"gated": req.gated, "passMark": float(req.pass_mark) if req.pass_mark is not None else None,
            "requirement": req.label, "requirementVersion": req.version}


def enrolment_dict(e: Enrolment, docs: dict | None = None, book=None, tests: dict | None = None):
    req = (book or requirements.Book()).for_enrolment(e)
    return {
        "ref": e.reference, "learner": e.learner.names, "learnerRef": e.learner.reference,
        "course": e.course.title, **requirement_dict(req),
        "intake": iso(e.plan_block.start_date) if e.plan_block_id else None,
        "intakeRef": e.plan_block.reference if e.plan_block_id else None,
        "stageIndex": e.stage_index, "stage": e.stage,
        "prerequisiteResult": float(e.prerequisite_result) if e.prerequisite_result is not None else None,
        "grade10": e.grade10_evidence_held,
        "grade10File": _evidence_dict(e, docs),
        "testFile": _evidence_dict(e, tests, kind="test"),
        "testAttempts": _attempts(e),
        "basis": {"PerLearner": "Per learner", "PerGroup": "Per group", "UniversityAgreement": "University agreement",
                  "Employee": "Employee"}[e.basis],
        "gateBlockedBy": gate_blockers(e, req) if e.stage_index == 0 else [],
        "advanceBlockedBy": advance_blockers(e, req),
        "owner": e.assigned_to.display_name if e.assigned_to_id else None,
    }


def _evidence_dict(e: Enrolment, docs: dict | None = None, kind: str = "grade10"):
    if docs is not None:
        doc = docs.get(e.reference)
    else:
        doc = evidence.current_test(e) if kind == "test" else evidence.current(e)
    if doc is None:
        return None
    return {"ref": doc.reference, "name": doc.title.split(" · ", 1)[-1], "type": doc.storage_key.rsplit(".", 1)[-1].upper(),
            "uploadedAt": stamp(doc.created_at), "uploadedBy": doc.created_by.display_name if doc.created_by_id else None,
            "url": f"/api/fsa/enrolments/{e.reference}/{kind}"}


def _attempts(e: Enrolment):
    """Every sitting of the prerequisite test, first to latest. A result from before attempts were kept is the first."""
    rows = list(e.prerequisite_attempts.all())
    out = [{"n": i + 1, "result": float(a.result), "capturedAt": stamp(a.created_at),
            "capturedBy": a.created_by.display_name if a.created_by_id else None,
            "file": {"name": a.document.title.split(" · ", 1)[-1], "url": f"/api/fsa/enrolments/{e.reference}/test/{i + 1}"}
            if a.document_id else None} for i, a in enumerate(rows)]
    if not out and e.prerequisite_result is not None:
        out = [{"n": 1, "result": float(e.prerequisite_result), "capturedAt": None, "capturedBy": None, "file": None}]
    return out


def _enrolments():
    return Enrolment.objects.filter(is_active=True).select_related("learner", "course__prior_course", "plan_block", "assigned_to").prefetch_related(
        "prerequisite_attempts__document", "prerequisite_attempts__created_by")


@router.get("/enrolments")
def enrolments(request):
    require(request, "learners")
    from assurance.models import Document

    docs = {d.entity_ref: d for d in Document.objects.filter(is_active=True, entity_type=evidence.ENTITY_TYPE).select_related("created_by")}
    tests = {d.entity_ref: d for d in Document.objects.filter(is_active=True, entity_type=evidence.TEST_TYPE).select_related("created_by")}
    book = requirements.Book()
    rows = [enrolment_dict(e, docs, book, tests) for e in _enrolments().order_by("-created_at", "-reference")]  # newest first
    return ok({"stages": ENR_STAGES, "items": rows,
               "counts": [sum(1 for r in rows if r["stageIndex"] == i) for i in range(len(ENR_STAGES))]},
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
    if body.grade10EvidenceHeld is False and body.prerequisiteResult is None:
        audit = evidence.remove(request.user, e, screen=_screen(request, "enrolments"))
    else:
        audit = services.update_gate(request.user, e, body.prerequisiteResult, body.grade10EvidenceHeld,
                                     screen=_screen(request, "enrolments"))
    return ok(enrolment_dict(e), audit=audit)


def _enrolment_or_404(ref):
    e = _enrolments().filter(reference=ref).first()
    if not e:
        raise Refusal("not_found", [f"No enrolment {ref}."], "Not found.", status=404)
    return e


@router.post("/enrolments/{ref}/grade10")
def upload_grade10(request, ref: str, file: File[UploadedFile]):
    """Upload (or replace) the Grade 10 document. Accepted: PDF, JPG or PNG, up to 5 MB, read by content."""
    require(request, "learners", write=True)
    e = _enrolment_or_404(ref)
    content = file.read(settings.FSA_UPLOAD_MAX_BYTES + 1)
    _, audit = evidence.attach(request.user, e, file.name, content, screen=_screen(request, "enrolments"))
    return ok(enrolment_dict(e), audit=audit)


@router.post("/enrolments/{ref}/test")
def capture_prerequisite_test(request, ref: str):
    """A new prerequisite test result with the marked test (multipart: result, file)."""
    require(request, "learners", write=True)
    e = _enrolment_or_404(ref)
    f = request.FILES.get("file")
    audit = evidence.capture_test(request.user, e, request.POST.get("result", ""), f.name if f else "",
                                  f.read(settings.FSA_UPLOAD_MAX_BYTES + 1) if f else b"", screen=_screen(request, "enrolments"))
    return ok(enrolment_dict(_enrolment_or_404(ref)), audit=audit)


@router.get("/enrolments/{ref}/test")
def view_prerequisite_test(request, ref: str):
    require(request, "learners")
    e = _enrolment_or_404(ref)
    doc = evidence.current_test(e)
    if doc is None or not evidence.path_of(doc).exists():
        raise Refusal("not_found", ["No prerequisite test is on file for this enrolment."], "Not found.", status=404)
    ext = doc.storage_key.rsplit(".", 1)[-1]
    response = FileResponse(evidence.path_of(doc).open("rb"), content_type=evidence.MEDIA_TYPE[ext])
    response["Content-Disposition"] = f'inline; filename="{e.reference}-prerequisite-test.{ext}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.get("/enrolments/{ref}/test/{n}")
def view_prerequisite_attempt(request, ref: str, n: int):
    """The marked test of attempt n (1 is the first sitting)."""
    require(request, "learners")
    e = _enrolment_or_404(ref)
    attempts = list(e.prerequisite_attempts.select_related("document"))
    doc = attempts[n - 1].document if 0 < n <= len(attempts) else None
    if doc is None or not evidence.path_of(doc).exists():
        raise Refusal("not_found", [f"No marked test is on file for attempt {n}."], "Not found.", status=404)
    ext = doc.storage_key.rsplit(".", 1)[-1]
    response = FileResponse(evidence.path_of(doc).open("rb"), content_type=evidence.MEDIA_TYPE[ext])
    response["Content-Disposition"] = f'inline; filename="{e.reference}-prerequisite-test-{n}.{ext}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.delete("/enrolments/{ref}/grade10")
def remove_grade10(request, ref: str):
    require(request, "learners", write=True)
    e = _enrolment_or_404(ref)
    audit = evidence.remove(request.user, e, screen=_screen(request, "enrolments"))
    return ok(enrolment_dict(e), audit=audit)


@router.get("/enrolments/{ref}/grade10")
def view_grade10(request, ref: str):
    """Stream the file to a signed-in user with the learners segment. Never a public URL."""
    require(request, "learners")
    e = _enrolment_or_404(ref)
    doc = evidence.current(e)
    if doc is None or not evidence.path_of(doc).exists():
        raise Refusal("not_found", ["No Grade 10 document is on file for this enrolment."], "Not found.", status=404)
    ext = doc.storage_key.rsplit(".", 1)[-1]
    response = FileResponse(evidence.path_of(doc).open("rb"), content_type=evidence.MEDIA_TYPE[ext])
    response["Content-Disposition"] = f'inline; filename="{e.reference}-grade10.{ext}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def result_dict(r: Result, actor=None, after: Result | None = None, before: Result | None = None, ctx: dict | None = None):
    m = getattr(r, "moderation", None)
    cert = getattr(m, "certificate", None) if m else None
    if cert:
        position, tone = f"Issued {cert.reference}", "ok"
    elif m and m.outcome == "Competent":
        position, tone = "Moderated — awaiting certificate", "info"
    elif m and after is not None:
        position, tone = f"Re-assessed on {after.reference}", "info"
    elif m:
        position, tone = "Moderated — remediation", "warn"
    else:
        position, tone = "Awaiting moderation", "warn"
    ctx = ctx if ctx is not None else {}
    doc = ctx.get("docs", {}).get(r.reference) if "docs" in ctx else assessment.evidence(r)
    key = r.enrolment_id
    if key not in ctx.setdefault("attendance", {}):
        ctx["attendance"][key] = assessment.attendance(r.enrolment)
    return {
        "ref": r.reference, "learner": r.enrolment.learner.names, "learnerRef": r.enrolment.learner.reference,
        "enrolment": r.enrolment.reference, "course": r.enrolment.course.title,
        "intake": r.enrolment.plan_block.reference if r.enrolment.plan_block_id else None,
        "session": r.session.reference if r.session_id else None,
        "assessor": r.assessed_by.display_name, "assessedAt": stamp(r.assessed_at, "%Y-%m-%d"),
        "mark": float(r.mark), "outcome": r.outcome,
        "moderated": m is not None, "moderatedOutcome": m.outcome if m else None,
        "moderatedBy": m.moderated_by.display_name if m else None,
        "moderatedAt": stamp(m.moderated_at, "%Y-%m-%d") if m else None, "moderationNotes": m.notes if m else "",
        "certificate": cert.reference if cert else None,
        "position": position, "tone": tone,
        "certificateBlockedBy": certificate_blockers(r),
        "remediation": r.remediation_plan,
        "reassesses": before.reference if before else None, "reassessedOn": after.reference if after else None,
        "evidence": {"ref": doc.reference, "title": doc.title.rsplit(" · ", 1)[-1], "url": f"/api/fsa/results/{r.reference}/assessment"}
        if doc else None,
        "attendance": ctx["attendance"][key],
        "ownAssessment": actor is not None and r.assessed_by_id == actor.pk,
    }


def _results():
    return Result.objects.filter(is_active=True).select_related(
        "enrolment__learner", "enrolment__course", "enrolment__plan_block", "session", "assessed_by",
        "moderation__moderated_by", "moderation__certificate")


def _scoped_results(request):
    qs = _results()
    if request.user.scope("results") == "own":
        qs = qs.filter(session__plan_block__facilitator=request.user) | qs.filter(assessed_by=request.user) \
            | qs.filter(enrolment__plan_block__facilitator=request.user)
    return qs.distinct()


def _result_rows(request, qs):
    """Rows with each result's place in its learner's attempts: the one it re-assesses, and the one that re-assessed it."""
    from assurance.models import Document

    rows = list(qs)
    attempts = {}
    for r in Result.objects.filter(is_active=True, enrolment_id__in={r.enrolment_id for r in rows}).order_by("assessed_at", "id"):
        attempts.setdefault(r.enrolment_id, []).append(r)
    docs = {d.entity_ref: d for d in Document.objects.filter(is_active=True, entity_type=assessment.EVIDENCE,
                                                               entity_ref__in=[r.reference for r in rows])}
    ctx = {"docs": docs, "attendance": {}}
    out = []
    for r in rows:
        chain = attempts.get(r.enrolment_id, [])
        i = next((n for n, x in enumerate(chain) if x.pk == r.pk), 0)
        out.append(result_dict(r, request.user, after=chain[i + 1] if i + 1 < len(chain) else None,
                               before=chain[i - 1] if i > 0 else None, ctx=ctx))
    return out


@router.get("/results")
def results(request):
    require(request, "results")
    rows = _result_rows(request, _scoped_results(request).order_by("-assessed_at", "-id"))
    return ok({"items": rows, "canModerate": request.user.can("moderation", write=True),
               "canCapture": request.user.can("results", write=True)},
              source="Assessment results · moderation records")


@router.get("/results/options")
def result_options(request):
    """The learners this person can capture a result for, grouped by intake, each with where they stand."""
    require(request, "results", write=True)
    enrolments = list(assessment.assessable(request.user).select_related("plan_block__course").order_by("plan_block__start_date", "learner__names"))
    latest = {}
    for r in Result.objects.filter(is_active=True, enrolment__in=enrolments).select_related("moderation").order_by("assessed_at", "id"):
        latest[r.enrolment_id] = r
    intakes = {}
    for e in enrolments:
        b = e.plan_block
        group = intakes.setdefault(b.pk, {"ref": b.reference, "course": e.course.title, "start": iso(b.start_date), "learners": []})
        r = latest.get(e.pk)
        m = getattr(r, "moderation", None) if r else None
        if b.start_date > clock.today():
            state, note = "notStarted", f"Intake starts {b.start_date.isoformat()}"
        elif r is None:
            state, note = "ready", "Not assessed yet"
        elif m is None:
            state, note = "awaiting", f"{r.reference} awaiting moderation"
        elif m.outcome == "Competent":
            state, note = "done", f"Competent on {r.reference}"
        else:
            state, note = "reassess", f"Re-assessment after {r.reference}"
        group["learners"].append({"enrolment": e.reference, "learner": e.learner.names, "state": state, "note": note,
                                  "attendance": assessment.attendance(e)})
    return ok({"intakes": list(intakes.values())}, source="Confirmed learners on intakes")


@router.post("/results")
def capture_result(request):
    """Capture a mark and outcome with the marked assessment (multipart: enrolment, mark, outcome, notes, file)."""
    require(request, "results", write=True, message="Results are captured by the assessor.")
    f = request.FILES.get("file")
    content = f.read(settings.FSA_UPLOAD_MAX_BYTES + 1) if f else b""
    r, audit = assessment.capture(request.user, enrolment_ref=request.POST.get("enrolment", ""), mark=request.POST.get("mark", ""),
                                  outcome=request.POST.get("outcome", ""), notes=request.POST.get("notes", ""),
                                  filename=f.name if f else "", content=content, screen=_screen(request, "results"))
    return ok(_result_rows(request, _results().filter(pk=r.pk))[0], audit=audit)


def _result_or_404(request, ref):
    r = _scoped_results(request).filter(reference=ref).first() if request.user.scope("results") == "own" \
        else _results().filter(reference=ref).first()
    if not r:
        raise Refusal("not_found", [f"No result {ref}."], "Not found.", status=404)
    return r


@router.post("/results/{ref}/assessment")
def replace_assessment(request, ref: str, file: File[UploadedFile]):
    require(request, "results", write=True)
    r = _result_or_404(request, ref)
    audit = assessment.replace_evidence(request.user, r, file.name, file.read(settings.FSA_UPLOAD_MAX_BYTES + 1),
                                        screen=_screen(request, "results"))
    return ok(_result_rows(request, _results().filter(pk=r.pk))[0], audit=audit)


@router.get("/results/{ref}/assessment")
def view_assessment(request, ref: str):
    """The marked assessment, streamed to a signed-in user who can see the result. Never a public URL."""
    require(request, "results")
    r = _result_or_404(request, ref)
    doc = assessment.evidence(r)
    if doc is None or not assessment.evidence_path(doc).exists():
        raise Refusal("not_found", ["No assessment is on file for this result."], "Not found.", status=404)
    ext = doc.storage_key.rsplit(".", 1)[-1]
    response = FileResponse(assessment.evidence_path(doc).open("rb"), content_type=assessment.media_type(doc))
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{r.reference}-assessment.{ext}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


class Moderate(Schema):
    outcome: str | None = None
    notes: str = ""
    remediation: str = ""
    reassessBy: str | None = None


@router.post("/results/{ref}/moderate")
def moderate(request, ref: str, body: Moderate):
    require(request, "moderation", write=True, message="Moderation is recorded by the training manager or a moderator.")
    r = _results().filter(reference=ref).first()
    if not r:
        raise Refusal("not_found", [f"No result {ref}."], "Not found.", status=404)
    if body.outcome not in (None, "Competent", "NotYetCompetent"):
        raise Refusal("invalid", ["The outcome is Competent or NotYetCompetent."], "Check the outcome.", status=422)
    reassess_by = None
    if body.reassessBy:
        try:
            reassess_by = dt.date.fromisoformat(body.reassessBy)
        except ValueError:
            raise Refusal("invalid", ["The re-assessment date is not a date."], "Check the date.", status=422)
        if reassess_by < clock.today():
            raise Refusal("invalid", ["The re-assessment date is in the past."], "Check the date.", status=422)
    audit = assessment.moderate(request.user, r, outcome=body.outcome, notes=body.notes, remediation=body.remediation,
                                reassess_by=reassess_by, screen=_screen(request, "results"))
    return ok(_result_rows(request, _results().filter(pk=r.pk))[0], audit=audit)


def certificate_dict(c: Certificate):
    r = c.moderation.result
    return {
        "ref": c.reference, "result": r.reference, "learner": r.enrolment.learner.names,
        "course": r.enrolment.course.title, "mark": float(r.mark),
        "issuedAt": stamp(c.issued_at, "%Y-%m-%d"), "issuedBy": c.issued_by.display_name,
        "verificationCode": c.verification_code,
        "depositoryRef": c.document.reference if c.document_id else None,
        "revoked": c.revoked_at is not None,
        "learnerRef": r.enrolment.learner.reference, "enrolment": r.enrolment.reference,
        "pdf": f"/api/fsa/certificates/{c.reference}/pdf",
    }


@router.get("/certificates")
def certificates(request):
    require(request, "certification")
    issued = [certificate_dict(c) for c in Certificate.objects.select_related(
        "moderation__result__enrolment__learner", "moderation__result__enrolment__course", "issued_by", "document")]
    pending = [result_dict(r) for r in _results().filter(moderation__certificate__isnull=True)]
    return ok({"issued": issued, "candidates": pending, "canIssue": request.user.can("certification", write=True)},
              source="Certification register · moderation records")


@router.get("/certificates/{ref}/pdf")
def certificate_pdf(request, ref: str, download: bool = False):
    """The certificate as a PDF, to view in the browser or (download=true) save."""
    require(request, "certification")
    from django.http import HttpResponse

    from learners.certificate_pdf import render

    cert = (Certificate.objects.select_related("moderation__result__enrolment__learner", "moderation__result__enrolment__course",
                                               "issued_by").filter(reference=ref).first())
    if cert is None:
        raise Refusal("not_found", [f"No certificate {ref}."], "Not found.", status=404)
    response = HttpResponse(render(cert), content_type="application/pdf")
    name = f"{cert.reference} {cert.moderation.result.enrolment.learner.names}.pdf".replace("/", "-")
    response["Content-Disposition"] = f'{"attachment" if download else "inline"}; filename="{name}"'
    response["X-Frame-Options"] = "SAMEORIGIN"  # shown inside the hub's own Certification page
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


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
def learners(request, idNumber: str | None = None):
    """The directory. With idNumber, only the learner holding that SA ID or passport number: the number
    is matched on its keyed hash, so the search works without ever decrypting a stored number."""
    require(request, "learners")
    from learners.models import Learner

    qs = Learner.objects.filter(is_active=True).order_by("-created_at", "-reference").select_related("organisation")  # newest first.prefetch_related("enrolments__course", "enrolments__plan_block")
    if idNumber is not None:
        digits = idNumber.replace(" ", "").replace("-", "")
        identity, problem = pii.parse("SAID" if digits.isdigit() and len(digits) == 13 else "Passport", idNumber)
        if identity is None:
            raise Refusal("invalid", [f"That is not a valid SA ID or passport number: {problem or 'enter a number'}."],
                          "Check the number.", status=422)
        qs = qs.filter(id_number_hmac=pii.blind_index(identity))
    rows = [{
        "ref": l.reference, "name": l.names, "type": l.learner_type,
        "organisation": l.organisation.name if l.organisation_id else "",
        "hrLinked": l.hr_person_id is not None,
        "idNumber": pii.mask(l.id_type, l.id_last4) or "Not captured",
        "studentNumber": l.external_ref,
        "enrolments": [f"{e.reference} · {e.course.title} · {e.stage}" for e in l.enrolments.all()],
        "enrolmentItems": [{"ref": e.reference, "course": e.course.title, "courseCode": e.course.code, "stage": e.stage,
                            "intakeRef": e.plan_block.reference if e.plan_block_id else None}
                           for e in l.enrolments.all() if e.is_active],
    } for l in qs]
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
    book = requirements.Book()
    return ok([{
        "ref": b.reference, "courseCode": b.course.code, "course": b.course.title, **requirement_dict(book.for_block(b)),
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


class UniversityIn(Schema):
    name: str
    body: str | None = None


@router.post("/universities")
def add_university(request, body: UniversityIn):
    from assurance import placements
    from core.models import Body

    require(request, "assurance", write=True, message="University partners are added by the training manager.")
    b = Body.objects.filter(code=body.body).first() if body.body else None
    if body.body and b is None:
        raise Refusal("invalid", [f"No body {body.body}."], "Check the body.", status=422)
    uni, audit = placements.add_university(request.user, body.name, b, screen=_screen(request, "partnerships"))
    return ok({"ref": uni.reference, "name": uni.name, "rule": uni.facilitator_body_id}, audit=audit)


@router.get("/universities")
def universities(request):
    from demand.models import Organisation

    require(request, "learners")
    return ok([{"ref": o.reference, "name": o.name}
               for o in Organisation.objects.filter(is_active=True, relationship="University").order_by("name")])


# --- course evaluations -------------------------------------------------------------------------------

@router.get("/feedback")
def feedback_register(request):
    """Every intake that has ended, with whom its evaluation has gone to and the scores so far. Who said what is
    not shown: only whether each learner has answered, so they can be reminded."""
    from delivery.models import PlanBlock
    from learners import evaluations
    from learners.models import Evaluation

    require(request, "learners")
    today = clock.today()
    evaluations.request_for_ended(today)
    rows = []
    blocks = (PlanBlock.objects.filter(enrolments__evaluation__isnull=False).distinct()
              .select_related("course", "facilitator", "venue").order_by("-end_date"))
    for b in blocks:
        evs = list(Evaluation.objects.filter(enrolment__plan_block=b).select_related("enrolment__learner__contact", "enrolment__learner"))
        s = evaluations.summary(evs)
        rows.append({
            "intake": b.reference, "course": b.course.title, "facilitator": b.facilitator.display_name, "venue": b.venue.name,
            "ended": iso(b.end_date), **s,
            "learners": [{"name": (l := ev.enrolment.learner).names,
                          "email": l.email or (l.contact.email if l.contact_id else ""),
                          "phone": l.phone or (l.contact.phone if l.contact_id else ""),
                          "answered": ev.submitted_at is not None, "link": f"/evaluate/{ev.token}"} for ev in
                         sorted(evs, key=lambda x: x.enrolment.learner.names)],
            "comments": [ev.comments for ev in evs if ev.submitted_at and ev.comments],
        })
    return ok({"items": rows, "dimensions": [{"key": k, "label": l} for k, l in evaluations.DIMENSIONS],
               "byFacilitator": evaluations.by_facilitator()}, source="Course evaluations · intakes")


@router.get("/public/feedback/{token}", auth=None)
def public_feedback(request, token: str):
    from learners import evaluations

    return ok(evaluations.public_view(token))


class FeedbackIn(Schema):
    content: int | None = None
    facilitation: int | None = None
    venue: int | None = None
    organisation: int | None = None
    recommend: bool | None = None
    comments: str = ""


@router.post("/public/feedback/{token}", auth=None)
def public_feedback_submit(request, token: str, body: FeedbackIn):
    from learners import evaluations

    evaluations.submit(token, body.dict())
    return ok({"received": True})
