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
                f"{fac.display_name}’s {reg.registration_type.lower()} lapsed on {reg.expires_on.isoformat()}. "
                "Scheduling is blocked — the block cannot be confirmed until the registration is renewed."
            )
    if fac.state == "Suspended" and not reasons:
        reasons.append(f"{fac.display_name}’s account is suspended — {fac.suspended_reason}.")
    return reasons


def block_warnings(block, others, on: dt.date | None = None) -> list[dict]:
    """Derived warnings on a plan block: fill, accreditation, clash. Never stored."""
    on = on or clock.today()
    out = []
    if block.capacity and block.seats_booked / block.capacity < 0.5:
        out.append({
            "kind": "fill", "tone": "warn",
            "message": f"{block.seats_booked} of {block.capacity} seats booked — below half, follow up the quotation.",
        })
    for reason in confirm_blockers(block, on):
        out.append({"kind": "accreditation", "tone": "bad", "message": reason})
    reg = block.facilitator.current_registration()
    if reg and max(on, block.start_date) <= reg.expires_on <= block.end_date:
        out.append({
            "kind": "accreditation", "tone": "warn",
            "message": f"{block.facilitator.display_name}’s {reg.registration_type.lower()} expires on "
                       f"{reg.expires_on.isoformat()}, inside this block. Renew before delivery.",
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
    block = session.plan_block
    if hasattr(session, "register"):
        return "Locked", "ok"
    if block.end_date < on:
        return "Outstanding", "bad"
    if block.start_date <= on:
        return "In progress", "info"
    return "Not yet delivered", "na"


def can_capture(session, on: dt.date | None = None) -> list[str]:
    on = on or clock.today()
    if hasattr(session, "register"):
        return ["This register was already captured and locked. A change is recorded as a correction."]
    if session.plan_block.start_date > on:
        return [f"The session starts on {session.plan_block.start_date.isoformat()}. A register is captured once delivery has begun."]
    return []
