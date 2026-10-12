import datetime as dt

from django.db.models import Count, Q
from ninja import Router, Schema

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
        "start": iso(b.start_date), "end": iso(b.end_date), "mode": b.delivery_mode,
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
        for a in s.attendance.filter(supersedes__isnull=False).select_related("learner", "captured_by")
    ]
    learners = [{
        "ref": l.reference, "name": l.names,
        "kind": l.learner_type + (f" — {l.organisation.name}" if l.organisation_id else ""),
        "present": current[l.id].present if l.id in current else None,
        "corrected": bool(current.get(l.id) and current[l.id].supersedes_id),
    } for l in services.roster(s)]
    d = session_dict(s, today)
    d.update(learners=learners, corrections=corrections, captureBlockedBy=can_capture(s, today),
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
        "ref": b.reference, "session": b.session.reference if hasattr(b, "session") else None,
        "course": b.course.title, "stream": b.stream.name, "streamCode": b.stream_id, "streamColour": b.stream.colour,
        "facilitator": b.facilitator.display_name, "venue": b.venue.name, "mode": b.delivery_mode,
        "cadence": b.intake_cadence, "start": iso(b.start_date), "end": iso(b.end_date),
        "seats": b.seats_booked, "capacity": b.capacity,
        "fill": round(100 * b.seats_booked / b.capacity) if b.capacity else 0,
        "hours": b.practical_hours, "notes": b.notes, "state": b.state,
        "warnings": block_warnings(b, others, today),
        "confirmBlockedBy": confirm_blockers(b, today) if b.state == "Draft" else [],
    }


def _blocks():
    return list(PlanBlock.objects.filter(is_active=True).select_related("course", "stream", "facilitator", "venue", "session")
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
    for a in Account.objects.filter(is_active=True, registrations__isnull=False).distinct().prefetch_related("registrations__body"):
        reg = a.current_registration()
        standing = reg.standing(today)
        blocks = list(PlanBlock.objects.filter(facilitator=a, is_active=True, end_date__gte=today).exclude(state="Cancelled")
                      .values_list("reference", flat=True))
        if standing == "Lapsed":
            position, tone = ("Finding — scheduled while lapsed" if blocks else "Lapsed — not scheduled"), "bad"
        elif standing == "Expiring":
            position, tone = "Observation — renew within ninety days", "warn"
        else:
            position, tone = "Compliant", "ok"
        rows.append({"ref": a.reference, "name": a.display_name, "registration": reg.registration_type,
                     "body": reg.body.name, "expires": iso(reg.expires_on), "blocks": blocks,
                     "position": position, "tone": tone})
    return ok(rows, source="Facilitator registrations · training plan")
