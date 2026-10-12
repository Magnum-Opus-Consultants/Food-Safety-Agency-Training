from django.db import transaction

from audit.services import record
from core import clock
from core.api_support import Refusal
from delivery.models import Attendance, AttendanceRegister
from delivery.rules import can_capture, confirm_blockers
from learners.models import Learner


def roster(session):
    """Learners registered onto the session's block (Registered stage or later)."""
    return (
        Learner.objects.filter(enrolments__plan_block_id=session.plan_block_id, enrolments__stage_index__gte=2,
                               enrolments__is_active=True)
        .select_related("organisation").distinct().order_by("reference")
    )


def effective_attendance(session) -> dict[int, Attendance]:
    """The latest row per learner: originals not superseded, or the correction that replaced them."""
    rows = list(session.attendance.all().select_related("captured_by"))
    superseded = {r.supersedes_id for r in rows if r.supersedes_id}
    return {r.learner_id: r for r in rows if r.id not in superseded}


@transaction.atomic
def capture_register(actor, session, marks: dict[str, bool], screen="sessions"):
    """Rule 3: the register locks on save. Every rostered learner must be marked first."""
    blocked = can_capture(session)
    if blocked:
        raise Refusal("register_locked" if hasattr(session, "register") else "not_started", blocked,
                      "This register cannot be captured.")
    learners = list(roster(session))
    missing = [l.names for l in learners if l.reference not in marks]
    if missing:
        raise Refusal("register_incomplete", [f"{n} is not marked present or absent" for n in missing],
                      "Mark every learner present or absent before saving.")
    unknown = set(marks) - {l.reference for l in learners}
    if unknown:
        raise Refusal("not_on_roster", [f"{r} is not on this session's roster" for r in sorted(unknown)],
                      "The register can only include rostered learners.")
    at = clock.now()
    Attendance.objects.bulk_create([
        Attendance(session=session, learner=l, present=bool(marks[l.reference]), captured_at=at, captured_by=actor)
        for l in learners
    ])
    AttendanceRegister.objects.create(session=session, locked_at=at, locked_by=actor)
    present = sum(1 for l in learners if marks[l.reference])
    return record(actor, f"{session.reference} attendance register captured and locked — {present} of {len(learners)} present",
                  session, screen=screen, after={"marks": marks})


@transaction.atomic
def correct_attendance(actor, session, learner_ref: str, present: bool, reason: str, screen="sessions"):
    """A correction after capture is a new audited entry, never an edit of the original."""
    if not hasattr(session, "register"):
        raise Refusal("register_not_locked", ["A correction applies only to a captured and locked register."],
                      "Capture the register first.")
    if not reason.strip():
        raise Refusal("reason_required", ["State why the attendance is being corrected."], "A correction needs a reason.")
    current = effective_attendance(session)
    learner = next((l for l in roster(session) if l.reference == learner_ref), None)
    if learner is None or learner.id not in current:
        raise Refusal("not_on_roster", [f"{learner_ref} is not on this register"], "Nothing to correct.")
    previous = current[learner.id]
    Attendance.objects.create(session=session, learner=learner, present=present, captured_at=clock.now(),
                              captured_by=actor, supersedes=previous, correction_reason=reason.strip())
    return record(
        actor,
        f"{session.reference} attendance corrected for {learner.names}: {'absent' if previous.present else 'present'} "
        f"→ {'present' if present else 'absent'} — {reason.strip()}",
        session, screen=screen, before={"present": previous.present}, after={"present": present},
    )


@transaction.atomic
def confirm_block(actor, block, screen="plan"):
    """Rule 5: hard block. The block cannot be confirmed while the registration is lapsed."""
    reasons = confirm_blockers(block)
    if reasons:
        raise Refusal("registration_lapsed", reasons, "This block cannot be confirmed.")
    if block.state == "Confirmed":
        raise Refusal("already_confirmed", [f"{block.reference} is already confirmed."], "Nothing to confirm.")
    block.state, block.confirmed_at, block.confirmed_by = "Confirmed", clock.now(), actor
    block.modified_by = actor
    block.save()
    return record(actor, f"{block.reference} confirmed — {block.course.title}, {block.start_date.isoformat()}",
                  block, screen=screen, before={"state": "Draft"}, after={"state": "Confirmed"})
