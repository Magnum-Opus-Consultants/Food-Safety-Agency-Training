from django.db.models import Count, Q
import datetime as dt

from django.conf import settings
from ninja import File, Router, Schema
from ninja.files import UploadedFile

from assurance.models import ACC_STEPS, Accreditation, AccreditationProject, Library, Placement, Risk
from core import clock
from core.api_support import Refusal, iso, ok, require, stamp

router = Router(tags=["assurance"])


@router.get("/depository")
def depository(request):
    require(request, "depository")
    libs = Library.objects.select_related("owner").annotate(
        held=Count("documents", filter=Q(documents__state="Held", documents__is_active=True)),
        outstanding=Count("documents", filter=Q(documents__state="Outstanding", documents__is_active=True)),
    )
    rows = [{
        "code": l.code, "name": l.name, "holds": l.holds, "count": l.held, "outstanding": l.outstanding,
        "retention": l.retention_rule, "owner": l.owner.display_name if l.owner_id else None,
        "position": f"{l.outstanding} outstanding" if l.outstanding else "Compliant",
        "tone": "bad" if l.outstanding else "ok",
    } for l in libs]
    outstanding = [{"ref": d.reference, "title": d.title, "library": d.library.name}
                   for lib in libs for d in lib.documents.filter(state="Outstanding", is_active=True)]
    return ok({"libraries": rows, "outstanding": outstanding}, source="Training depository")


def _held_dict(a, today):
    from assurance import workflow

    position, tone = workflow.standing(a, today)
    cert = workflow.certificate(a)
    return {
        "ref": a.reference, "body": a.body.name, "bodyCode": a.body_id, "scope": a.scope, "number": a.number,
        "granted": iso(a.granted_on), "expires": iso(a.expires_on), "tone": tone, "position": position,
        "courses": [{"code": c.code, "title": c.title} for c in a.courses.all().order_by("title")],
        "renewing": [{"ref": p.reference, "step": ACC_STEPS[p.step_index]} for p in a.renewal_projects.filter(is_active=True, state="Active")],
        "certificate": {"name": cert.title.split(" · ", 1)[-1], "url": f"/api/fsa/accreditations/{a.reference}/certificate"} if cert else None,
    }


def _project_dict(p, today):
    from assurance import workflow

    docs = workflow.step_documents(p)

    position, tone = workflow.step_state(p, today)
    due = list(p.step_due) + [None] * (len(ACC_STEPS) - len(p.step_due))
    done = list(p.step_done) + [None] * (len(ACC_STEPS) - len(p.step_done))
    notes = list(p.step_notes) + [""] * (len(ACC_STEPS) - len(p.step_notes))
    return {
        "ref": p.reference, "body": p.body.name, "bodyCode": p.body_id, "scope": p.scope, "owner": p.owner.display_name,
        "ownerRef": p.owner.reference, "target": iso(p.target_date), "step": p.step_index, "steps": ACC_STEPS, "state": p.state,
        "position": position, "tone": tone, "renews": p.renews.reference if p.renews_id else None,
        "result": p.result.reference if p.result_id else None,
        "courses": [{"code": c.code, "title": c.title} for c in p.courses.all().order_by("title")],
        "plan": [{"step": s, "due": iso(due[i]), "done": iso(done[i]) if (i < p.step_index or p.state == "Accredited") else None,
                  "note": notes[i], "hint": workflow.STEP_DOC_HINT[i],
                  "documents": [{"ref": d.reference, "title": d.title.rsplit(" · ", 1)[-1], "added": iso(d.created_at.date()),
                                 "url": f"/api/fsa/accreditation-projects/{p.reference}/documents/{d.reference}"} for d in docs[i]],
                  "late": bool(due[i] and ((done[i] and done[i] > due[i] and i < p.step_index)
                                                       or (i == p.step_index and p.state == "Active" and due[i] < today)))}
                 for i, s in enumerate(ACC_STEPS)],
        "notes": p.notes,
    }


@router.get("/accreditations")
def accreditations(request):
    require(request, "assurance")
    from assurance import workflow

    today = clock.today()
    held = [_held_dict(a, today) for a in workflow.current_held().select_related("body").prefetch_related("courses").order_by("expires_on")]
    projects = [_project_dict(p, today) for p in AccreditationProject.objects.filter(is_active=True)
                .select_related("body", "owner", "renews", "result").prefetch_related("courses").order_by("state", "target_date")]
    return ok({"held": held, "projects": projects,
               "canManage": request.user.can("assurance", write=True), "me": request.user.reference},
              source="Accreditation register")


@router.get("/accreditations/options")
def accreditation_options(request):
    require(request, "assurance")
    from core.models import Body
    from courses.models import Course
    from identity.models import Account

    return ok({
        "bodies": [{"code": b.code, "name": b.name} for b in Body.objects.order_by("name")],
        "courses": [{"code": c.code, "title": c.title} for c in Course.objects.filter(is_active=True).order_by("title")],
        "people": [{"ref": a.reference, "name": a.display_name} for a in Account.objects.filter(is_active=True, is_service_account=False)
                   .exclude(hub_role="Learner").order_by("display_name")],
        "steps": ACC_STEPS,
    })


def _held_or_404(ref):
    a = Accreditation.objects.filter(reference=ref, is_active=True).select_related("body").first()
    if a is None:
        raise Refusal("not_found", [f"No accreditation {ref}."], "Not found.", status=404)
    return a


def _project_or_404(ref):
    p = AccreditationProject.objects.filter(reference=ref, is_active=True).select_related("body", "owner", "renews").first()
    if p is None:
        raise Refusal("not_found", [f"No application {ref}."], "Not found.", status=404)
    return p


def _scr(request):
    return request.headers.get("X-FSA-Screen", "accreditation")


@router.get("/accreditations/{ref}")
def accreditation_detail(request, ref: str):
    """One accreditation: what it covers, its history of renewals, and the intakes that depend on it."""
    require(request, "assurance")
    from delivery.models import PlanBlock

    a = _held_or_404(ref)
    today = clock.today()
    history, cur = [], a
    while cur is not None:
        history.append({"ref": cur.reference, "number": cur.number, "granted": iso(cur.granted_on), "expires": iso(cur.expires_on),
                         "recorded": stamp(cur.created_at), "by": cur.created_by.display_name if cur.created_by_id else "System"})
        cur = cur.renews
    intakes = (PlanBlock.objects.filter(course__in=a.courses.all(), is_active=True, end_date__gte=today).exclude(state="Cancelled")
               .select_related("course").order_by("start_date"))
    return ok({**_held_dict(a, today), "history": history,
               "intakes": [{"ref": b.reference, "course": b.course.title, "start": iso(b.start_date), "end": iso(b.end_date),
                            "covered": a.expires_on >= b.end_date} for b in intakes]})


class HeldIn(Schema):
    body: str = ""
    scope: str = ""
    number: str = ""
    granted: dt.date | None = None
    expires: dt.date | None = None
    courses: list[str] = []


@router.post("/accreditations")
def add_accreditation(request, body: HeldIn):
    require(request, "assurance")
    from assurance import workflow

    a, audit = workflow.add_held(request.user, body_code=body.body, scope=body.scope, number=body.number, granted_on=body.granted,
                                 expires_on=body.expires, course_codes=body.courses, screen=_scr(request))
    return ok({"ref": a.reference}, audit=audit)


class RenewIn(Schema):
    number: str = ""
    granted: dt.date | None = None
    expires: dt.date | None = None


@router.post("/accreditations/{ref}/renew")
def renew_accreditation(request, ref: str, body: RenewIn):
    require(request, "assurance")
    from assurance import workflow

    a, audit = workflow.renew_held(request.user, _held_or_404(ref), number=body.number, granted_on=body.granted,
                                   expires_on=body.expires, screen=_scr(request))
    return ok({"ref": a.reference}, audit=audit)


class CoursesIn(Schema):
    courses: list[str] = []


@router.put("/accreditations/{ref}/courses")
def accreditation_courses(request, ref: str, body: CoursesIn):
    require(request, "assurance")
    from assurance import workflow

    audit = workflow.set_courses(request.user, _held_or_404(ref), body.courses, screen=_scr(request))
    return ok({"ref": ref}, audit=audit)


@router.post("/accreditations/{ref}/certificate")
def accreditation_certificate(request, ref: str, file: File[UploadedFile]):
    require(request, "assurance")
    from django.conf import settings

    from assurance import workflow

    _, audit = workflow.attach_certificate(request.user, _held_or_404(ref), file.name, file.read(settings.FSA_UPLOAD_MAX_BYTES + 1),
                                           screen=_scr(request))
    return ok({"ref": ref}, audit=audit)


@router.get("/accreditations/{ref}/certificate")
def view_accreditation_certificate(request, ref: str):
    require(request, "assurance")
    from django.conf import settings
    from django.http import FileResponse
    from pathlib import Path

    from assurance import workflow
    from learners.evidence import MEDIA_TYPE

    doc = workflow.certificate(_held_or_404(ref))
    path = Path(settings.FSA_FILE_ROOT) / doc.storage_key if doc else None
    if doc is None or not path.exists():
        raise Refusal("not_found", ["No certificate is on file for this accreditation."], "Not found.", status=404)
    ext = doc.storage_key.rsplit(".", 1)[-1]
    response = FileResponse(path.open("rb"), content_type=MEDIA_TYPE[ext])
    response["Content-Disposition"] = f'inline; filename="{ref}-certificate.{ext}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class ProjectIn(Schema):
    body: str = ""
    scope: str = ""
    owner: str = ""
    target: dt.date | None = None
    courses: list[str] = []
    renews: str = ""
    due: list[dt.date | None] = []


@router.post("/accreditation-projects")
def start_project(request, body: ProjectIn):
    require(request, "assurance")
    from assurance import workflow

    p, audit = workflow.start_project(request.user, body_code=body.body, scope=body.scope, owner_ref=body.owner, target_date=body.target,
                                      course_codes=body.courses, renews_ref=body.renews, step_due=body.due or None, screen=_scr(request))
    return ok({"ref": p.reference}, audit=audit)


class StepIn(Schema):
    note: str = ""
    number: str = ""
    granted: dt.date | None = None
    expires: dt.date | None = None


@router.post("/accreditation-projects/{ref}/step")
def complete_step(request, ref: str, body: StepIn):
    require(request, "assurance")
    from assurance import workflow

    p, audit = workflow.complete_step(request.user, _project_or_404(ref), note=body.note, number=body.number,
                                      granted_on=body.granted, expires_on=body.expires, screen=_scr(request))
    return ok(_project_dict(p, clock.today()), audit=audit)


class ReplanIn(Schema):
    owner: str | None = None
    target: dt.date | None = None
    due: list[dt.date | None] | None = None


@router.patch("/accreditation-projects/{ref}")
def replan_project(request, ref: str, body: ReplanIn):
    require(request, "assurance")
    from assurance import workflow

    p, audit = workflow.replan(request.user, _project_or_404(ref), owner_ref=body.owner, target_date=body.target, step_due=body.due,
                               screen=_scr(request))
    return ok(_project_dict(p, clock.today()), audit=audit)


class WithdrawIn(Schema):
    reason: str = ""


@router.post("/accreditation-projects/{ref}/steps/{n}/documents")
def application_step_document(request, ref: str, n: int, file: File[UploadedFile]):
    """File a document against step n (1 to 6) of an application."""
    from assurance import workflow

    require(request, "assurance")
    p = _project_or_404(ref)
    _, audit = workflow.attach_step_document(request.user, p, n - 1, file.name, file.read(settings.FSA_UPLOAD_MAX_BYTES + 1),
                                             screen=request.headers.get("X-FSA-Screen", "accreditation"))
    return ok(_project_dict(_project_or_404(ref), clock.today()), audit=audit)


@router.get("/accreditation-projects/{ref}/documents/{doc}")
def application_document(request, ref: str, doc: str):
    from django.http import FileResponse

    from assurance import workflow
    from assurance.models import Document

    require(request, "assurance")
    d = Document.objects.filter(is_active=True, reference=doc, entity_ref=ref, entity_type__startswith=workflow.STEP_DOCS).first()
    from pathlib import Path

    path = Path(settings.FSA_FILE_ROOT) / d.storage_key if d else None
    if path is None or not path.exists():
        raise Refusal("not_found", [f"No document {doc} on {ref}."], "Not found.", status=404)
    ext = d.storage_key.rsplit(".", 1)[-1]
    from learners.evidence import MEDIA_TYPE

    response = FileResponse(path.open("rb"), content_type=MEDIA_TYPE.get(ext, "application/octet-stream"))
    response["Content-Disposition"] = f'{"attachment" if request.GET.get("download") else "inline"}; filename="{d.reference}.{ext}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.post("/accreditation-projects/{ref}/withdraw")
def withdraw_project(request, ref: str, body: WithdrawIn):
    require(request, "assurance")
    from assurance import workflow

    audit = workflow.withdraw(request.user, _project_or_404(ref), body.reason, screen=_scr(request))
    return ok({"ref": ref}, audit=audit)


def _can_run_placements(user):
    return user.can("learners", write=True) or user.can("assurance", write=True)


def placement_dict(p):
    from assurance import placements

    roster = placements.students(p)
    position, tone = placements.standing(p)
    block = p.plan_block
    docs = placements.documents(p)
    return {
        "ref": p.reference, "university": p.organisation.name, "universityRef": p.organisation.reference,
        "cohort": p.cohort_label, "size": p.cohort_size, "periodStart": iso(p.period_start), "periodEnd": iso(p.period_end),
        "reportDue": iso(p.report_due), "position": position, "tone": tone,
        "intake": block.reference if block else None, "abattoir": block.venue.name if block else None,
        "facilitator": block.facilitator.display_name if block else None,
        "rule": p.organisation.facilitator_body_id,
        "students": roster, "checklist": placements.checklist(p, roster),
        "documents": [{"ref": d.reference, "kind": placements.KINDS[d.entity_type], "title": d.title.rsplit(" · ", 1)[-1],
                       "added": iso(d.created_at.date()), "url": f"/api/fsa/placements/{p.reference}/documents/{d.reference}"}
                      for d in docs],
        "reportBlockedBy": placements.report_blockers(p, roster),
        "reportPreview": f"/api/fsa/placements/{p.reference}/report",
    }


def _placements():
    return Placement.objects.filter(is_active=True).select_related(
        "organisation__facilitator_body", "plan_block__venue", "plan_block__course", "plan_block__facilitator")


@router.get("/partnerships")
def partnerships(request):
    from core.models import Body
    from demand.models import Organisation

    require(request, "assurance")
    rows = [placement_dict(p) for p in _placements().order_by("-period_start")]
    unis = [{"ref": o.reference, "name": o.name, "rule": o.facilitator_body_id,
             "placements": sum(1 for r in rows if r["universityRef"] == o.reference)}
            for o in Organisation.objects.filter(is_active=True, relationship="University").order_by("name")]
    return ok({"items": rows, "universities": unis, "bodies": [{"code": b.code, "name": b.name} for b in Body.objects.order_by("code")],
               "canRun": _can_run_placements(request.user), "canSetRules": request.user.can("assurance", write=True)},
              source="University placements register")


def _placement_for_write(request, ref):
    if not _can_run_placements(request.user):
        raise Refusal("forbidden", ["Placements are run by the training administrator or training manager."], "Not permitted.", status=403)
    p = _placements().filter(reference=ref).first()
    if p is None:
        raise Refusal("not_found", [f"No placement {ref}."], "Not found.", status=404)
    return p


def _screen(request, default):
    return request.headers.get("X-FSA-Screen", default)


@router.post("/placements/{ref}/abattoir-documents")
def placement_abattoir_document(request, ref: str, file: File[UploadedFile]):
    from assurance import placements

    p = _placement_for_write(request, ref)
    audit = placements.add_abattoir_document(request.user, p, file.name, file.read(settings.FSA_UPLOAD_MAX_BYTES + 1),
                                             screen=_screen(request, "partnerships"))
    return ok(placement_dict(_placements().get(pk=p.pk)), audit=audit)


class AbattoirConfirmed(Schema):
    on: str


@router.post("/placements/{ref}/abattoir-confirmed")
def placement_abattoir_confirmed(request, ref: str, body: AbattoirConfirmed):
    from assurance import placements

    p = _placement_for_write(request, ref)
    try:
        on = dt.date.fromisoformat(body.on)
    except ValueError:
        raise Refusal("invalid", ["Give the date the abattoir confirmed."], "Check the date.", status=422)
    audit = placements.confirm_abattoir(request.user, p, on, screen=_screen(request, "partnerships"))
    return ok(placement_dict(_placements().get(pk=p.pk)), audit=audit)


@router.get("/placements/{ref}/report")
def placement_report(request, ref: str):
    """The report as it stands: a preview before submission. After submission, the filed copy."""
    from django.http import HttpResponse

    from assurance import placements

    require(request, "assurance")
    p = _placements().filter(reference=ref).first()
    if p is None:
        raise Refusal("not_found", [f"No placement {ref}."], "Not found.", status=404)
    filed = placements.documents(p, placements.REPORT)
    pdf = placements.path_of(filed[-1]).read_bytes() if filed and placements.path_of(filed[-1]).exists() else placements.report_pdf(p, request.user)
    response = HttpResponse(pdf, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{p.reference} report — {p.organisation.name}.pdf"'
    response["Cache-Control"] = "no-store"
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


@router.post("/placements/{ref}/report")
def placement_submit_report(request, ref: str):
    from assurance import placements

    p = _placement_for_write(request, ref)
    audit = placements.submit_report(request.user, p, screen=_screen(request, "partnerships"))
    return ok(placement_dict(_placements().get(pk=p.pk)), audit=audit)


@router.get("/placements/{ref}/documents/{doc}")
def placement_document(request, ref: str, doc: str):
    from django.http import FileResponse

    from assurance import placements
    from assurance.models import Document

    require(request, "assurance")
    d = Document.objects.filter(is_active=True, reference=doc, entity_ref=ref, entity_type__in=list(placements.KINDS)).first()
    if d is None or not placements.path_of(d).exists():
        raise Refusal("not_found", [f"No document {doc} on {ref}."], "Not found.", status=404)
    ext = d.storage_key.rsplit(".", 1)[-1]
    response = FileResponse(placements.path_of(d).open("rb"), content_type=placements.media_type(d))
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{d.reference}.{ext}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


class Rule(Schema):
    body: str | None = None


@router.put("/universities/{ref}/rule")
def university_rule(request, ref: str, body: Rule):
    from assurance import placements
    from core.models import Body
    from demand.models import Organisation

    require(request, "assurance", write=True, message="University rules are set by the training manager.")
    uni = Organisation.objects.filter(is_active=True, relationship="University", reference=ref).first()
    if uni is None:
        raise Refusal("not_found", [f"No university {ref}."], "Not found.", status=404)
    b = Body.objects.filter(code=body.body).first() if body.body else None
    if body.body and b is None:
        raise Refusal("invalid", [f"No body {body.body}."], "Check the body.", status=422)
    audit = placements.set_requirement(request.user, uni, b, screen=_screen(request, "partnerships"))
    return ok({"ref": uni.reference, "rule": uni.facilitator_body_id}, audit=audit)


@router.get("/risks")
def risks(request):
    require(request, "assurance")
    rows = [{"ref": r.reference, "risk": r.risk, "cause": r.cause, "rating": r.rating, "trigger": r.escalation_trigger,
             "breached": r.trigger_breached_at is not None, "owner": r.owner.display_name, "position": r.position,
             "tone": "bad" if r.rating == "High" or r.trigger_breached_at else ("warn" if r.rating == "Medium" else "ok")}
            for r in Risk.objects.filter(is_active=True).select_related("owner")]
    return ok(rows, source="Risk and escalation register")
