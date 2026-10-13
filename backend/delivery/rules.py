"""Delivery rules. Pure functions: they read state and return reasons, never write."""
import datetime as dt

from core import clock


def confirm_blockers(block, on: dt.date | None = None) -> list[str]:
    """Rule 5: a facilitator whose registration has lapsed cannot be scheduled. Hard block."""
    on = on or clock.today()
    fac = block.facilitator
    regs = [r for r in fac.registrations.all() if r.is_active]
    required = block.course.required_registration_type
    if required:
        regs = [r for r in regs if r.registration_type == required]
    reasons = []
    if not regs:
        reasons.append(f"{fac.display_name} holds no registration for this course. Scheduling is blocked.")
    else:
        reg = max(regs, key=lambda r: r.expires_on)
        if reg.expires_on < max(on, block.start_date):
            reasons.append(
                f"{fac.display_name}’s {reg.registration_type.lower()} {'lapsed' if reg.expires_on < on else 'lapses'} on "
                f"{reg.expires_on.isoformat()}, before this intake runs. "
                "The intake cannot be confirmed until the registration is renewed."
            )
    if fac.state == "Suspended" and not reasons:
        reasons.append(f"{fac.display_name}’s account is suspended — {fac.suspended_reason}.")
    return reasons


def block_warnings(block, others, on: dt.date | None = None) -> list[dict]:
    """Derived warnings on an intake: fill, the facilitator's registration, clashes. Never stored.

    A finished or cancelled intake carries none: there is nothing left to act on. Fill matters only
    before the intake starts. The facilitator's registration is judged against the intake's own
    dates (it must be valid while the intake runs), not against today's date alone."""
    on = on or clock.today()
    if block.state == "Cancelled" or block.end_date < on:
        return []
    out = []
    if block.start_date > on and block.capacity and block.seats_booked / block.capacity < 0.5:
        out.append({
            "kind": "fill", "tone": "warn",
            "message": f"{block.seats_booked} of {block.capacity} seats booked — below half, follow up the quotation.",
        })
    for reason in confirm_blockers(block, on):
        if block.state == "Confirmed":
            reason = reason.replace("The intake cannot be confirmed until the registration is renewed.",
                                    "Renew it, or give the intake to another facilitator, before delivery.")
        out.append({"kind": "accreditation", "tone": "bad", "message": reason})
    reg = block.facilitator.current_registration()
    if reg and max(on, block.start_date) <= reg.expires_on < block.end_date:
        out.append({
            "kind": "accreditation", "tone": "warn",
            "message": f"{block.facilitator.display_name}’s {reg.registration_type.lower()} expires on "
                       f"{reg.expires_on.isoformat()}, while this intake is running. Renew before delivery.",
        })
    for other in others:
        if (other.pk != block.pk and other.facilitator_id == block.facilitator_id and other.state != "Cancelled"
                and other.start_date <= block.end_date and other.end_date >= block.start_date):
            out.append({
                "kind": "clash", "tone": "warn",
                "message": f"{block.facilitator.display_name} is also booked on {other.reference} "
                           f"({other.start_date.isoformat()} to {other.end_date.isoformat()}).",
            })
    return out


def register_state(session, on: dt.date | None = None) -> tuple[str, str]:
    """Locked / Outstanding (finding once delivered) / In progress / Not yet delivered.

    "Delivered" means the block has ended. This matches the monthly report's count of two
    outstanding registers on 2026-09-09; the prototype counted from the start date (open item).
    """
    on = on or clock.today()
    if hasattr(session, "register"):
        return "Locked", "ok"
    if session.last_day < on:
        return "Outstanding", "bad"
    if session.first_day <= on:
        return "In progress" if session.day is None else "Today", "info"
    return "Not yet delivered", "na"


def can_capture(session, on: dt.date | None = None) -> list[str]:
    on = on or clock.today()
    if hasattr(session, "register"):
        return ["This register was already captured and locked. A change is recorded as a correction."]
    if session.first_day > on:
        return [f"The session is on {session.first_day.isoformat()}. A register is captured once delivery has begun."]
    from delivery.services import not_on_roster, roster

    if not roster(session).exists():
        waiting = not_on_roster(session)
        return ["Nobody is confirmed onto this session yet, so there is no one to mark. A register is not locked empty."] + [
            f"{w['learner']} ({w['enrolment']}) is {w['stage'].lower()}, not yet confirmed: {w['why']}." for w in waiting]
    return []
