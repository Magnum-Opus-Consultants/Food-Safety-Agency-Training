import datetime as dt

from django.db.models import Count, Q
from ninja import File, Router, Schema
from ninja.files import UploadedFile

from core import clock
from core.api_support import Refusal, iso, ok, require, stamp
from delivery import services
from delivery.models import PlanBlock, Session
from delivery.rules import block_warnings, can_capture, confirm_blockers, register_state
from identity.models import Account

router = Router(tags=["delivery"])

SESSION_RELATED = ("plan_block__course", "plan_block__facilitator", "plan_block__venue", "register__locked_by")


def _screen(request, default):
    return request.headers.get("X-FSA-Screen", default)


def _own_session_or_refuse(request, session):
    if request.user.scope("delivery") == "own" and session.plan_block.facilitator_id != request.user.pk:
        raise Refusal("not_your_session", [f"{session.reference} is facilitated by "
                                           f"{session.plan_block.facilitator.display_name}."],
                      "Facilitators capture registers for their own sessions only.", status=403)


def session_dict(s: Session, today):
    b = s.plan_block
    state, tone = register_state(s, today)
    return {
        "ref": s.reference, "block": b.reference, "course": b.course.title, "venue": b.venue.name,
        "facilitator": b.facilitator.display_name, "facilitatorRef": b.facilitator.reference,
        "start": iso(s.first_day), "end": iso(s.last_day), "mode": b.delivery_mode,
        "day": iso(s.day), "sequence": s.sequence, "of": b.sessions.filter(is_active=True).count() if s.day else None,
        "times": f"{b.starts_at:%H:%M}–{b.ends_at:%H:%M}" if b.starts_at and b.ends_at else "",
        "seats": b.seats_booked, "capacity": b.capacity,
        "registerState": state, "tone": tone,
        "lockedAt": stamp(s.register.locked_at) if hasattr(s, "register") else None,
        "lockedBy": s.register.locked_by.display_name if hasattr(s, "register") else None,
    }


@router.get("/sessions")
def sessions(request):
    require(request, "delivery")
    today = clock.today()
    qs = Session.objects.filter(is_active=True).exclude(plan_block__state="Cancelled").select_related(*SESSION_RELATED)
    own = request.user.scope("delivery") == "own"
    if own:
        qs = qs.filter(plan_block__facilitator=request.user)
    rows = [session_dict(s, today) for s in qs]
    outstanding = sum(1 for r in rows if r["registerState"] == "Outstanding")
    return ok({
        "items": rows,
        "scope": "own" if own else "all",
        "stats": [
            {"v": str(len(rows)), "l": "Sessions", "c": "Your sessions" if own else "In the plan"},
            {"v": str(sum(1 for r in rows if r["registerState"] == "Locked")), "l": "Registers locked", "c": "Captured and locked on save"},
            {"v": str(outstanding), "l": "Outstanding", "c": "Delivered without a captured register"},
            {"v": str(sum(1 for r in rows if r["registerState"] == "In progress")), "l": "In progress", "c": "Delivery under way"},
        ],
    }, source="Training plan · attendance registers")


@router.get("/sessions/{ref}")
def session_detail(request, ref: str):
    require(request, "delivery")
    s = Session.objects.select_related(*SESSION_RELATED).filter(reference=ref).first()
    if not s:
        raise Refusal("not_found", [f"No session {ref}."], "Not found.", status=404)
    _own_session_or_refuse(request, s)
    today = clock.today()
    current = services.effective_attendance(s)
    corrections = [
        {"learner": a.learner.names, "present": a.present, "reason": a.correction_reason,
         "at": stamp(a.captured_at), "by": a.captured_by.display_name}
        for a in s.attendance.filter(Q(supersedes__isnull=False) | Q(late_entry=True)).select_related("learner", "captured_by")
    ]
    learners = [{
        "ref": l.reference, "name": l.names,
        "kind": l.learner_type + (f" — {l.organisation.name}" if l.organisation_id else ""),
        "present": current[l.id].present if l.id in current else None,
        "corrected": bool(current.get(l.id) and current[l.id].supersedes_id),
        "late": bool(current.get(l.id) and current[l.id].late_entry),
    } for l in services.roster(s)]
    d = session_dict(s, today)
    d.update(learners=learners, corrections=corrections, captureBlockedBy=can_capture(s, today),
             notOnRoster=services.not_on_roster(s),
             canWrite=request.user.can("delivery", write=True))
    return ok(d)


class RegisterCapture(Schema):
    marks: dict[str, bool]


@router.post("/sessions/{ref}/attendance")
def capture(request, ref: str, body: RegisterCapture):
    require(request, "delivery", write=True)
    s = Session.objects.select_related(*SESSION_RELATED).filter(reference=ref).first()
    if not s:
        raise Refusal("not_found", [f"No session {ref}."], "Not found.", status=404)
    _own_session_or_refuse(request, s)
    audit = services.capture_register(request.user, s, body.marks, screen=_screen(request, "sessions"))
    s = Session.objects.select_related(*SESSION_RELATED).get(pk=s.pk)
    return ok(session_dict(s, clock.today()), audit=audit)


class LateEntry(Schema):
    learnerRef: str
    present: bool
    reason: str = ""


@router.post("/sessions/{ref}/attendance/late")
def late_entry(request, ref: str, body: LateEntry):
    require(request, "delivery", write=True)
    s = Session.objects.select_related(*SESSION_RELATED).filter(reference=ref).first()
    if not s:
        raise Refusal("not_found", [f"No session {ref}."], "Not found.", status=404)
    _own_session_or_refuse(request, s)
    audit = services.add_late_entry(request.user, s, body.learnerRef, body.present, body.reason, screen=_screen(request, "sessions"))
    return ok(session_dict(s, clock.today()), audit=audit)


class Correction(Schema):
    learnerRef: str
    present: bool
    reason: str


@router.post("/sessions/{ref}/attendance/correction")
def correction(request, ref: str, body: Correction):
    require(request, "delivery", write=True)
    s = Session.objects.select_related(*SESSION_RELATED).filter(reference=ref).first()
    if not s:
        raise Refusal("not_found", [f"No session {ref}."], "Not found.", status=404)
    _own_session_or_refuse(request, s)
    audit = services.correct_attendance(request.user, s, body.learnerRef, body.present, body.reason,
                                        screen=_screen(request, "sessions"))
    return ok(session_dict(s, clock.today()), audit=audit)


# --- the plan ----------------------------------------------------------------------------

def block_dict(b: PlanBlock, others, today):
    return {
        "ref": b.reference,
        "session": (lambda ss: (ss[0].reference if len(ss) == 1 else f"{len(ss)} sessions") if ss else None)(
            [x for x in b.sessions.all() if x.is_active]),
        "sessionCount": sum(1 for x in b.sessions.all() if x.is_active),
        "schedule": b.schedule, "weekdays": b.weekdays,
        "startsAt": b.starts_at.strftime("%H:%M") if b.starts_at else "", "endsAt": b.ends_at.strftime("%H:%M") if b.ends_at else "",
        "course": b.course.title, "stream": b.stream.name, "streamCode": b.stream_id, "streamColour": b.stream.colour,
        "facilitator": b.facilitator.display_name, "venue": b.venue.name, "mode": b.delivery_mode,
        "cadence": b.intake_cadence, "start": iso(b.start_date), "end": iso(b.end_date),
        "seats": b.seats_booked, "capacity": b.capacity,
        "fill": round(100 * b.seats_booked / b.capacity) if b.capacity else 0,
        "hours": b.practical_hours, "notes": b.notes, "state": b.state,
        "courseCode": b.course.code, "facilitatorRef": b.facilitator.reference, "venueId": b.venue_id,
        "started": b.start_date <= today,
        "warnings": block_warnings(b, others, today),
        "confirmBlockedBy": confirm_blockers(b, today) if b.state == "Draft" else [],
    }


def _blocks():
    return list(PlanBlock.objects.filter(is_active=True).select_related("course", "stream", "facilitator", "venue").prefetch_related("sessions")
                .prefetch_related("facilitator__registrations")
                .annotate(booked=Count("enrolments", filter=Q(enrolments__is_active=True))))


@router.get("/plan")
def plan(request, start: dt.date | None = None, end: dt.date | None = None, stream: str | None = None):
    require(request, "delivery")
    today = clock.today()
    blocks = _blocks()
    shown = [b for b in blocks if (not start or b.end_date >= start) and (not end or b.start_date <= end)
             and (not stream or b.stream_id == stream)]
    return ok([block_dict(b, blocks, today) for b in shown], source="Training plan")


@router.post("/plan/{ref}/confirm")
def confirm(request, ref: str):
    require(request, "delivery", write=True)
    if request.user.scope("delivery") == "own":
        raise Refusal("forbidden", ["Blocks are confirmed by the training manager."], "Not permitted.", status=403)
    blocks = _blocks()
    block = next((b for b in blocks if b.reference == ref), None)
    if not block:
        raise Refusal("not_found", [f"No plan block {ref}."], "Not found.", status=404)
    audit = services.confirm_block(request.user, block, screen=_screen(request, "plan"))
    return ok(block_dict(block, blocks, clock.today()), audit=audit)


@router.get("/facilitators")
def facilitators(request):
    """Registrations checked against the blocks each facilitator is scheduled to deliver."""
    require(request, "delivery")
    today = clock.today()
    rows = []
    people = Account.objects.filter(is_active=True, registrations__isnull=False).distinct().prefetch_related("registrations__body")
    if request.user.scope("delivery") == "own":
        people = people.filter(pk=request.user.pk)
    for a in people:
        reg = a.current_registration()
        standing = reg.standing(today)
        blocks = list(PlanBlock.objects.filter(facilitator=a, is_active=True, end_date__gte=today).exclude(state="Cancelled")
                      .values_list("reference", flat=True))
        if standing == "Lapsed":
            position, tone = ("Lapsed but still scheduled — renew now" if blocks else "Lapsed — not scheduled"), "bad"
        elif standing == "Expiring":
            position, tone = "Expires soon — renew within ninety days", "warn"
        else:
            position, tone = "In order", "ok"
        rows.append({"ref": a.reference, "name": a.display_name, "registration": reg.registration_type,
                     "body": reg.body.name, "expires": iso(reg.expires_on), "blocks": blocks,
                     "position": position, "tone": tone})
    return ok(rows, source="Facilitator registrations · training plan")


# --- planning intakes: add, change, cancel --------------------------------------------------

@router.get("/plan/options")
def plan_options(request):
    require(request, "delivery")
    from core.models import Venue
    from courses.models import Course
    from delivery.models import DELIVERY_MODES
    from delivery.planning import CADENCES, facilitator_options

    return ok({
        "courses": [{"code": c.code, "title": c.title, "days": c.duration_days, "mode": c.delivery_mode}
                    for c in Course.objects.filter(is_active=True).order_by("title")],
        "facilitators": [{"ref": a.reference, "name": a.display_name, "role": a.get_hub_role_display()} for a in facilitator_options()],
        "venues": [{"id": v.pk, "name": v.name} for v in Venue.objects.filter(is_active=True).order_by("name")],
        "modes": DELIVERY_MODES, "cadences": CADENCES,
        "canPlan": request.user.can("delivery", write=True) and request.user.scope("delivery") != "own",
    })


class IntakeFields(Schema):
    schedule: str = "Block"
    weekdays: list[int] = []
    startsAt: dt.time | None = None
    endsAt: dt.time | None = None
    courseCode: str = ""
    facilitatorRef: str = ""
    venueId: int | None = None
    newVenue: str = ""
    mode: str = ""
    cadence: str = "AdHoc"
    start: dt.date | None = None
    end: dt.date | None = None
    capacity: int | None = None
    hours: int | None = None
    notes: str = ""
    reason: str = ""


def _fields(body: IntakeFields):
    return {"courseCode": body.courseCode, "facilitatorRef": body.facilitatorRef, "venueId": body.venueId, "newVenue": body.newVenue,
            "mode": body.mode, "cadence": body.cadence, "start": body.start, "end": body.end, "capacity": body.capacity,
            "hours": body.hours, "notes": body.notes, "schedule": body.schedule, "weekdays": body.weekdays,
            "startsAt": body.startsAt, "endsAt": body.endsAt}


def _block_or_404(ref):
    block = PlanBlock.objects.filter(reference=ref, is_active=True).first()
    if block is None:
        raise Refusal("not_found", [f"No intake {ref}."], "Not found.", status=404)
    return block


def _fresh(ref):
    blocks = _blocks()
    return block_dict(next(b for b in blocks if b.reference == ref), blocks, clock.today())


@router.post("/plan")
def add_intake(request, body: IntakeFields):
    require(request, "delivery", write=True)
    from delivery.planning import create_intake

    block, audit = create_intake(request.user, _fields(body), screen=_screen(request, "plan"))
    return ok(_fresh(block.reference), audit=audit)


@router.patch("/plan/{ref}")
def change_intake(request, ref: str, body: IntakeFields):
    require(request, "delivery", write=True)
    from delivery.planning import edit_intake

    block, audit, affected = edit_intake(request.user, _block_or_404(ref), _fields(body), reason=body.reason,
                                         screen=_screen(request, "plan"))
    return ok(_fresh(block.reference), audit=audit, affected=affected)


class CancelIntake(Schema):
    reason: str = ""


@router.post("/plan/{ref}/cancel")
def cancel(request, ref: str, body: CancelIntake):
    require(request, "delivery", write=True)
    from delivery.planning import cancel_intake

    block, audit, affected = cancel_intake(request.user, _block_or_404(ref), body.reason, screen=_screen(request, "plan"))
    return ok(_fresh(block.reference), audit=audit, affected=affected)


@router.get("/plan/{ref}/learners")
def intake_learners(request, ref: str):
    """Who is registered on an intake and how to reach them: the list to tell when it moves."""
    require(request, "delivery")
    from delivery.planning import affected_learners

    return ok(affected_learners(_block_or_404(ref)))


# --- facilitator registrations: renew, add, certificate --------------------------------------

def _account_or_404(ref):
    a = Account.objects.filter(reference=ref, is_active=True).first()
    if a is None:
        raise Refusal("not_found", [f"No account {ref}."], "Not found.", status=404)
    return a


@router.get("/facilitators/options")
def facilitator_form_options(request):
    require(request, "delivery")
    from core.models import Body
    from delivery.planning import facilitator_options

    return ok({
        "bodies": [{"code": b.code, "name": b.name} for b in Body.objects.order_by("name")],
        "people": [{"ref": a.reference, "name": a.display_name, "role": a.get_hub_role_display(),
                    "registered": a.registrations.filter(is_active=True).exists()} for a in facilitator_options()],
        "canRecord": request.user.hub_role in ("TrainingManager", "SystemAdministrator"),
    })


@router.get("/facilitators/{ref}")
def facilitator_detail(request, ref: str):
    """One facilitator: every registration held (renewals are new rows), certificates, and what they deliver."""
    require(request, "delivery")
    from delivery.registrations import certificate

    a = _account_or_404(ref)
    if request.user.scope("delivery") == "own" and a.pk != request.user.pk:
        raise Refusal("forbidden", ["You can see your own registration."], "Not permitted.", status=403)
    today = clock.today()
    regs = []
    for r in a.registrations.filter(is_active=True).select_related("body").order_by("-expires_on"):
        doc = certificate(r)
        regs.append({"id": r.pk, "registration": r.registration_type, "body": r.body.name, "bodyCode": r.body_id,
                     "number": r.registration_no, "issued": iso(r.issued_on), "expires": iso(r.expires_on), "standing": r.standing(today),
                     "recorded": stamp(r.created_at), "recordedBy": r.created_by.display_name if r.created_by_id else "System",
                     "certificate": {"name": doc.title.split(" · ", 1)[-1], "url": f"/api/fsa/facilitators/registrations/{r.pk}/certificate"}
                     if doc else None})
    blocks = (PlanBlock.objects.filter(facilitator=a, is_active=True, end_date__gte=today).exclude(state="Cancelled")
              .select_related("course").order_by("start_date"))
    return ok({
        "ref": a.reference, "name": a.display_name, "role": a.get_hub_role_display(), "state": a.state,
        "suspendedReason": a.suspended_reason, "registrations": regs,
        "intakes": [{"ref": b.reference, "course": b.course.title, "start": iso(b.start_date), "end": iso(b.end_date), "state": b.state}
                    for b in blocks],
    })


class RegistrationIn(Schema):
    registrationType: str = ""
    body: str = ""
    number: str = ""
    issued: dt.date | None = None
    expires: dt.date | None = None


@router.post("/facilitators/{ref}/registrations")
def add_registration(request, ref: str, body: RegistrationIn):
    require(request, "delivery")
    from delivery.registrations import record_registration

    reg, audit = record_registration(request.user, _account_or_404(ref), registration_type=body.registrationType, body_code=body.body,
                                     number=body.number, issued_on=body.issued, expires_on=body.expires,
                                     screen=_screen(request, "facilitators"))
    return ok({"id": reg.pk}, audit=audit)


@router.post("/facilitators/registrations/{reg_id}/certificate")
def upload_certificate(request, reg_id: int, file: File[UploadedFile]):
    require(request, "delivery")
    from django.conf import settings

    from delivery.registrations import attach_certificate
    from identity.models import FacilitatorRegistration

    reg = FacilitatorRegistration.objects.filter(pk=reg_id, is_active=True).select_related("account").first()
    if reg is None:
        raise Refusal("not_found", ["No such registration."], "Not found.", status=404)
    _, audit = attach_certificate(request.user, reg, file.name, file.read(settings.FSA_UPLOAD_MAX_BYTES + 1),
                                  screen=_screen(request, "facilitators"))
    return ok({"id": reg.pk}, audit=audit)


@router.get("/facilitators/registrations/{reg_id}/certificate")
def view_certificate(request, reg_id: int):
    require(request, "delivery")
    from django.http import FileResponse

    from delivery.registrations import certificate, media_type, path_of
    from identity.models import FacilitatorRegistration

    reg = FacilitatorRegistration.objects.filter(pk=reg_id, is_active=True).first()
    doc = certificate(reg) if reg else None
    if doc is None or not path_of(doc).exists():
        raise Refusal("not_found", ["No certificate is on file for this registration."], "Not found.", status=404)
    response = FileResponse(path_of(doc).open("rb"), content_type=media_type(doc))
    response["Content-Disposition"] = f'inline; filename="registration-{reg_id}.{doc.storage_key.rsplit(".", 1)[-1]}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
