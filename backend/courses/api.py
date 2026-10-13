import datetime as dt

from ninja import Router, Schema

from audit.models import AuditEntry
from core import clock
from core.api_support import Refusal, iso, ok, require, stamp
from core.models import Body, Service, Stream
from courses import requirements, services
from courses.models import ENTRY_GATES, Course

router = Router(tags=["courses"])


def _screen(request, default="catalogue"):
    return request.headers.get("X-FSA-Screen", default)


def _version_dict(r):
    return {"version": r.version, "from": iso(r.effective_from) if r.effective_from.year > 2000 else None,
            "kind": r.kind, "label": r.label, "passMark": float(r.pass_mark) if r.pass_mark is not None else None,
            "priorCourse": r.prior_course.code if r.prior_course_id else None, "description": r.description,
            "reason": r.reason, "by": r.created_by.display_name if r.created_by_id else "System", "at": stamp(r.created_at)}


def course_dict(c: Course, book: requirements.Book):
    current = book.current(c.pk)
    upcoming = book.scheduled(c.pk)
    return {
        "code": c.code, "title": c.title, "service": c.service.name, "serviceCode": c.service_id, "stream": c.stream.name,
        "streamCode": c.stream_id, "streamColour": c.stream.colour, "days": c.duration_days, "mode": c.delivery_mode,
        "entryRequirement": current.label if current else "None", "gated": bool(current and current.gated),
        "passMark": float(current.pass_mark) if current and current.pass_mark is not None else None,
        "requirementVersion": current.version if current else None,
        "upcoming": [{"from": iso(r.effective_from), "label": r.label, "version": r.version} for r in upcoming],
        "accredited": c.is_accredited, "body": c.accreditation_body.name if c.accreditation_body_id else None,
        "bodyCode": c.accreditation_body_id,
    }


def _course(code):
    c = Course.objects.filter(code=code, is_active=True).select_related("service", "stream", "accreditation_body").first()
    if c is None:
        raise Refusal("not_found", [f"No course {code} in the catalogue."], "Not found.", status=404)
    return c


@router.get("/courses")
def courses(request):
    require(request, "courses")
    book = requirements.Book()
    rows = [course_dict(c, book) for c in Course.objects.filter(is_active=True).select_related("service", "stream", "accreditation_body")]
    # A facilitator works from the courses they deliver: those they are scheduled on, now or later.
    from delivery.models import PlanBlock

    mine = sorted(set(PlanBlock.objects.filter(facilitator=request.user, is_active=True, end_date__gte=clock.today())
                      .exclude(state="Cancelled").values_list("course__code", flat=True)))
    delivers = request.user.hub_role in ("Facilitator", "Assessor", "Moderator")
    return ok(rows, source="Course catalogue", mine=mine, focusMine=delivers)


@router.get("/courses/options")
def options(request):
    require(request, "courses")
    return ok({
        "services": [{"code": s.code, "name": s.name} for s in Service.objects.order_by("name")],
        "streams": [{"code": s.code, "name": s.name} for s in Stream.objects.order_by("sort_order")],
        "bodies": [{"code": b.code, "name": b.name} for b in Body.objects.order_by("name")],
        "kinds": [{"code": k, "label": l} for k, l in ENTRY_GATES],
        "courses": [{"code": c.code, "title": c.title} for c in Course.objects.filter(is_active=True)],
    })


@router.get("/courses/{code}")
def course_detail(request, code: str):
    """One course: its details, every version of its entry requirement, which intakes are locked to
    their requirement because learners are registered, and the full edit trail."""
    require(request, "courses")
    c = _course(code)
    book = requirements.Book()
    locked = requirements.locked_intakes(c)
    trail = AuditEntry.objects.filter(entity_type="courses.course", entity_ref=c.code).order_by("-at", "-id")
    return ok({
        **course_dict(c, book),
        "versions": [_version_dict(r) for r in reversed(book.by_course.get(c.pk, []))],
        "lockedIntakes": [{"ref": b.reference, "start": iso(b.start_date), "requirement": book.for_block(b).label,
                           "learners": b.enrolments.filter(is_active=True).count()} for b in locked if b.end_date >= clock.today()],
        "earliestChange": iso(requirements.earliest_change(c)),
        "trail": [e.as_dict() for e in trail] if request.user.can_see_audit else [],
        "trailVisible": request.user.can_see_audit,
        "canEdit": request.user.can("courses", write=True),
    })


class CourseDetails(Schema):
    title: str
    service: str
    stream: str
    days: int | None = None
    mode: str = ""
    body: str = ""


class RequirementIn(Schema):
    kind: str
    passMark: float | None = None
    priorCourse: str = ""
    description: str = ""


class NewCourse(CourseDetails, RequirementIn):
    code: str


class RequirementChange(RequirementIn):
    effectiveFrom: dt.date
    reason: str = ""


@router.post("/courses")
def add_course(request, body: NewCourse):
    require(request, "courses", write=True, message="Courses are added by the head of department.")
    course, audit = services.create_course(
        request.user, code=body.code, title=body.title, service=body.service, stream=body.stream, days=body.days,
        mode=body.mode, body=body.body, kind=body.kind, pass_mark=body.passMark, prior_code=body.priorCourse,
        description=body.description, screen=_screen(request))
    return ok(course_dict(_course(course.code), requirements.Book()), audit=audit)


@router.patch("/courses/{code}")
def edit_course(request, code: str, body: CourseDetails):
    require(request, "courses", write=True, message="Courses are edited by the head of department.")
    course, audit = services.update_course(request.user, _course(code), title=body.title, service=body.service,
                                           stream=body.stream, days=body.days, mode=body.mode, body=body.body,
                                           screen=_screen(request))
    return ok(course_dict(_course(code), requirements.Book()), audit=audit)


@router.post("/courses/{code}/requirements")
def change_requirement(request, code: str, body: RequirementChange):
    require(request, "courses", write=True, message="Entry requirements are changed by the head of department.")
    _, audit = services.change_requirement(
        request.user, _course(code), kind=body.kind, pass_mark=body.passMark, prior_code=body.priorCourse,
        description=body.description, effective_from=body.effectiveFrom, reason=body.reason, screen=_screen(request))
    return ok(course_dict(_course(code), requirements.Book()), audit=audit)
