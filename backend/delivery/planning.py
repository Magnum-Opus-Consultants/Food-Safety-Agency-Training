"""Planning intakes: add, change, and cancel. Every change is audited.

An intake that has started is no longer changed here (its register belongs to Sessions). A change of
dates, venue or facilitator on an intake that already has learners is a postponement or a move: a
reason is required, and the learners affected are returned so they can be told. Seats booked are
derived from enrolments, so capacity can never drop below the learners already registered."""

import datetime as dt

from django.db import transaction

from audit.services import record
from core import clock
from core.api_support import Refusal
from core.models import Venue
from courses.models import Course
from delivery.models import DELIVERY_MODES, SCHEDULES, WEEKDAY_NAMES, PlanBlock
from delivery.schedule import meeting_dates, sync_sessions
from identity.models import Account

CADENCES = ["AdHoc", "Monthly", "Quarterly"]
FACILITATOR_ROLES = ("Facilitator", "Assessor", "Moderator", "TrainingManager")


def facilitator_options():
    return Account.objects.filter(is_active=True, hub_role__in=FACILITATOR_ROLES, is_service_account=False).order_by("display_name")


def _planner(actor):
    if not actor.can("delivery", write=True) or actor.scope("delivery") == "own":
        raise Refusal("forbidden", ["Intakes are planned by the head of department (the training manager)."], "Not permitted.",
                      status=403)


def affected_learners(block):
    """The people registered on an intake, with how to reach them (and their company's contact)."""
    rows = []
    for e in (block.enrolments.filter(is_active=True).select_related("learner__organisation", "quotation__contact")
              .order_by("learner__names")):
        l = e.learner
        rows.append({"enrolment": e.reference, "learner": l.names, "learnerRef": l.reference, "email": l.email, "phone": l.phone,
                     "company": l.organisation.name if l.organisation_id else "",
                     "companyContact": (f"{e.quotation.contact.names} {e.quotation.contact.email}".strip()
                                        if e.quotation_id else "")})
    return rows


def _venue(venue_id, new_venue):
    if new_venue and new_venue.strip():
        name = new_venue.strip()
        return Venue.objects.filter(name__iexact=name).first() or Venue.objects.create(name=name)
    return Venue.objects.filter(pk=venue_id, is_active=True).first() if venue_id else None


def _check(fields, block=None):
    """Validate the planning fields; returns reasons and the resolved objects."""
    today = clock.today()
    reasons = []
    course = Course.objects.filter(code=fields["courseCode"], is_active=True).first()
    if course is None:
        reasons.append("Choose the course.")
    fac = facilitator_options().filter(reference=fields["facilitatorRef"]).first()
    if fac is None:
        reasons.append("Choose the facilitator.")
    venue = _venue(fields.get("venueId"), fields.get("newVenue", ""))
    if venue is None:
        reasons.append("Choose the venue, or type a new one.")
    if fields["mode"] not in DELIVERY_MODES:
        reasons.append("Choose how it is delivered.")
    if fields["cadence"] not in CADENCES:
        reasons.append("Choose whether it is ad hoc, monthly or quarterly.")
    start, end = fields["start"], fields["end"]
    if start is None or end is None:
        reasons.append("Give the start and end dates.")
    else:
        if end < start:
            reasons.append("The end date is before the start date.")
        if start < today and (block is None or start != block.start_date):
            reasons.append("An intake cannot be planned to start in the past.")
    if not fields["capacity"] or fields["capacity"] < 1:
        reasons.append("Give the number of seats, at least one.")
    elif block is not None and fields["capacity"] < block.enrolments.filter(is_active=True).count():
        booked = block.enrolments.filter(is_active=True).count()
        reasons.append(f"{booked} learners are already registered, so the intake needs at least {booked} seats.")
    if fields.get("hours") is not None and fields["hours"] < 0:
        reasons.append("Practical hours cannot be negative.")
    schedule = fields.get("schedule") or "Block"
    if schedule not in dict(SCHEDULES):
        reasons.append("Choose how the intake meets: every weekday, set days each week, or one day.")
    elif schedule == "Weekly" and not fields.get("weekdays"):
        reasons.append("Choose the days of the week the class meets.")
    elif schedule == "Single" and start and end and end != start:
        reasons.append("A one-day intake starts and ends on the same day.")
    elif start and end and not reasons and not meeting_dates(schedule, fields.get("weekdays") or [], start, end):
        reasons.append("No meeting falls between those dates on the days chosen.")
    if fields.get("startsAt") and fields.get("endsAt") and fields["endsAt"] <= fields["startsAt"]:
        reasons.append("The class ends before it starts.")
    return reasons, course, fac, venue


def _schedule_text(block, n):
    if block.schedule == "Single":
        when = "one day"
    elif block.schedule == "Weekly":
        when = "every " + " and ".join(WEEKDAY_NAMES[d] for d in sorted(block.weekdays))
    else:
        when = "every weekday"
    times = f", {block.starts_at:%H:%M}–{block.ends_at:%H:%M}" if block.starts_at and block.ends_at else ""
    return f"{when}{times}: {n} {'session' if n == 1 else 'sessions'}"


@transaction.atomic
def create_intake(actor, fields, screen="plan"):
    _planner(actor)
    reasons, course, fac, venue = _check(fields)
    if reasons:
        raise Refusal("invalid", reasons, "The intake cannot be added yet.", status=422)
    block = PlanBlock.objects.create(
        course=course, stream=course.stream, facilitator=fac, venue=venue, delivery_mode=fields["mode"],
        intake_cadence=fields["cadence"], start_date=fields["start"], end_date=fields["end"], capacity=fields["capacity"],
        practical_hours=fields.get("hours") or 0, notes=(fields.get("notes") or "").strip(), state="Draft",
        schedule=fields.get("schedule") or "Block", weekdays=sorted(set(fields.get("weekdays") or [])),
        starts_at=fields.get("startsAt"), ends_at=fields.get("endsAt"), created_by=actor, modified_by=actor,
    )
    meetings = sync_sessions(block, actor)
    audit = record(actor, f"{block.reference} planned as a draft — {course.title}, {block.start_date.isoformat()} to "
                          f"{block.end_date.isoformat()}, {_schedule_text(block, len(meetings))}, {venue.name}, "
                          f"{fac.display_name}, {block.capacity} seats", block, screen=screen)
    return block, audit


@transaction.atomic
def edit_intake(actor, block, fields, reason="", screen="plan"):
    _planner(actor)
    block = PlanBlock.objects.select_for_update(of=("self",)).select_related("course", "facilitator", "venue").get(pk=block.pk)
    today = clock.today()
    if block.state == "Cancelled":
        raise Refusal("cancelled", [f"{block.reference} was cancelled; plan a new intake instead."], "Cancelled intakes are not changed.")
    if block.start_date <= today:
        raise Refusal("started", [f"{block.reference} started on {block.start_date.isoformat()}; a running or delivered intake "
                                  "is not re-planned."], "This intake has started.")
    reasons, course, fac, venue = _check(fields, block)
    learners = block.enrolments.filter(is_active=True).count()
    if course is not None and course.pk != block.course_id and learners:
        reasons.append(f"{learners} learners are registered for {block.course.title}; the course of this intake cannot change.")
    if reasons:
        raise Refusal("invalid", reasons, f"{block.reference} cannot be saved yet.", status=422)

    label = {"AdHoc": "ad hoc", "Monthly": "monthly", "Quarterly": "quarterly"}
    before = {"Course": block.course.title, "Facilitator": block.facilitator.display_name, "Venue": block.venue.name,
              "Delivery": block.delivery_mode, "Cadence": label[block.intake_cadence], "Start": block.start_date.isoformat(),
              "End": block.end_date.isoformat(), "Seats": str(block.capacity), "Practical hours": str(block.practical_hours),
              "Notes": block.notes, "Meets": _schedule_text(block, block.sessions.filter(is_active=True).count())}
    after = {"Course": course.title, "Facilitator": fac.display_name, "Venue": venue.name, "Delivery": fields["mode"],
             "Cadence": label[fields["cadence"]], "Start": fields["start"].isoformat(), "End": fields["end"].isoformat(),
             "Seats": str(fields["capacity"]), "Practical hours": str(fields.get("hours") or 0), "Notes": (fields.get("notes") or "").strip()}
    trial = PlanBlock(schedule=fields.get("schedule") or "Block", weekdays=sorted(set(fields.get("weekdays") or [])),
                      starts_at=fields.get("startsAt"), ends_at=fields.get("endsAt"))
    after["Meets"] = _schedule_text(trial, len(meeting_dates(trial.schedule, trial.weekdays, fields["start"], fields["end"])))
    changed = [k for k in after if after[k] != before[k]]
    if not changed:
        raise Refusal("no_change", ["Nothing was changed."], "There is nothing to save.")
    # Learners were told the dates, place and facilitator: changing those needs a reason, and they are listed to be told.
    moves = [k for k in changed if k in ("Start", "End", "Venue", "Facilitator")]
    if moves and learners and not reason.strip():
        raise Refusal("reason_needed", [f"{learners} learners are registered on {block.reference}. Give the reason for changing the "
                                        f"{', '.join(m.lower() for m in moves)}, so it is on record when they are told."],
                      "A reason is needed.", status=422)
    if block.state == "Confirmed" and fac.pk != block.facilitator_id:
        from delivery.rules import confirm_blockers

        trial = PlanBlock(course=course, facilitator=fac, start_date=fields["start"], end_date=fields["end"])
        blockers = confirm_blockers(trial, today)
        if blockers:
            raise Refusal("facilitator_lapsed", blockers, "This facilitator cannot take a confirmed intake.")

    block.course, block.stream, block.facilitator, block.venue = course, course.stream, fac, venue
    block.delivery_mode, block.intake_cadence = fields["mode"], fields["cadence"]
    block.start_date, block.end_date, block.capacity = fields["start"], fields["end"], fields["capacity"]
    block.practical_hours, block.notes = fields.get("hours") or 0, (fields.get("notes") or "").strip()
    block.schedule, block.weekdays = fields.get("schedule") or "Block", sorted(set(fields.get("weekdays") or []))
    block.starts_at, block.ends_at = fields.get("startsAt"), fields.get("endsAt")
    block.modified_by = actor
    block.row_version += 1
    block.save()
    meetings = sync_sessions(block, actor)
    after["Meets"] = _schedule_text(block, len(meetings))
    if after["Meets"] != before["Meets"] and "Meets" not in changed:
        changed.append("Meets")
    summary = "; ".join(f"{k.lower()} {before[k] or '—'} → {after[k] or '—'}" for k in changed if k != "Notes")
    if "Notes" in changed:
        summary = (summary + "; " if summary else "") + "notes updated"
    what = f"{block.reference} {'postponed' if 'Start' in moves else 'changed'} — {summary}"
    if moves and learners:
        what += f" — reason: {reason.strip()}; {learners} learners to be told"
    audit = record(actor, what, block, screen=screen, before={k: before[k] for k in changed}, after={k: after[k] for k in changed})
    return block, audit, (affected_learners(block) if moves and learners else [])


@transaction.atomic
def cancel_intake(actor, block, reason, screen="plan"):
    _planner(actor)
    block = PlanBlock.objects.select_for_update(of=("self",)).get(pk=block.pk)
    if block.state == "Cancelled":
        raise Refusal("cancelled", [f"{block.reference} is already cancelled."], "Nothing to cancel.")
    if block.start_date <= clock.today():
        raise Refusal("started", [f"{block.reference} started on {block.start_date.isoformat()}; it cannot be cancelled now."],
                      "This intake has started.")
    if not (reason or "").strip():
        raise Refusal("reason_needed", ["Give the reason for cancelling."], "A reason is needed.", status=422)
    affected = affected_learners(block)
    before = block.state
    block.state, block.modified_by = "Cancelled", actor
    block.notes = (block.notes + "\n" if block.notes else "") + f"Cancelled {clock.today().isoformat()}: {reason.strip()}"
    block.save()
    what = f"{block.reference} cancelled — {reason.strip()}"
    if affected:
        what += f"; {len(affected)} registered learners to be told and moved to another intake"
    return block, record(actor, what, block, screen=screen, before={"State": before}, after={"State": "Cancelled"}), affected
