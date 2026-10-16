"""Whether a facilitator is keeping up with their work, read from the registers, never from opinion.

Three indicators over the last six months of delivery:
  - Attendance registers: captured and locked within two working days of the session's last day, or late,
    or still outstanding.
  - Results: once an intake ends, every confirmed learner is assessed within ten working days.
  - Moderation: how often the moderator changed the facilitator's outcome. A pattern of changes
    means the marking needs attention.
Each indicator says what is behind and where, so the training manager can follow it up with the person.
"""

import datetime as dt

from core import clock

REGISTER_DAYS = 2
RESULT_DAYS = 10
WINDOW_DAYS = 183


def _late(done: dt.date, due_from: dt.date, allowed: int) -> bool:
    return clock.working_days_between(
        dt.datetime.combine(due_from, dt.time(10), tzinfo=dt.UTC), dt.datetime.combine(done, dt.time(10), tzinfo=dt.UTC)) > allowed


def _some(names: list[str], n: int = 4) -> str:
    return ", ".join(names[:n]) + (f" and {len(names) - n} more" if len(names) > n else "")


def indicators(account, on: dt.date | None = None) -> dict:
    from delivery.models import PlanBlock, Session
    from learners.models import Enrolment, Result

    on = on or clock.today()
    since = on - dt.timedelta(days=WINDOW_DAYS)
    blocks = list(PlanBlock.objects.filter(facilitator=account, is_active=True, end_date__gte=since, start_date__lte=on)
                  .exclude(state="Cancelled"))

    # Registers
    sessions = [s for s in Session.objects.filter(plan_block__in=blocks, is_active=True).select_related("register", "plan_block")
                if s.last_day < on]
    outstanding, late = [], []
    for s in sessions:
        reg = getattr(s, "register", None)
        if reg is None:
            if _late(on, s.last_day, REGISTER_DAYS):
                outstanding.append(s.reference)
        elif _late(clock.local_date(reg.locked_at), s.last_day, REGISTER_DAYS):
            late.append(s.reference)
    on_time = len(sessions) - len(outstanding) - len(late)

    # Results after the intake ends
    ended = [b for b in blocks if b.end_date < on and _late(on, b.end_date, RESULT_DAYS)]
    missing = []
    for b in ended:
        for e in Enrolment.objects.filter(plan_block=b, is_active=True, stage_index__gte=1).select_related("learner"):
            if not e.results.filter(is_active=True).exists():
                missing.append(f"{e.learner.names} ({b.reference})")

    # Moderation outcomes changed
    moderated = list(Result.objects.filter(assessed_by=account, is_active=True, moderation__isnull=False,
                                           moderation__moderated_at__date__gte=since).select_related("moderation"))
    changed = [r.reference for r in moderated if r.moderation.outcome != r.outcome]

    items = []
    if sessions:
        tone = "bad" if outstanding else "warn" if late else "ok"
        note = f"{on_time} of {len(sessions)} on time"
        if outstanding:
            note += f"; {len(outstanding)} outstanding ({', '.join(outstanding)})"
        if late:
            note += f"; {len(late)} captured late ({', '.join(late)})"
        items.append({"key": "registers", "label": "Attendance registers", "tone": tone, "note": note})
    if ended:
        items.append({"key": "results", "label": f"Results within {RESULT_DAYS} working days of the intake ending",
                      "tone": "bad" if missing else "ok",
                      "note": f"{len(missing)} {'learner' if len(missing) == 1 else 'learners'} not assessed: {_some(missing)}" if missing
                      else "All learners assessed"})
    if moderated:
        share = len(changed) / len(moderated)
        items.append({"key": "moderation", "label": "Outcomes upheld at moderation",
                      "tone": "bad" if len(changed) >= 2 and share >= 0.25 else "warn" if changed else "ok",
                      "note": f"{len(moderated) - len(changed)} of {len(moderated)} upheld"
                              + (f"; changed on {', '.join(changed)}" if changed else "")})
    # What learners said about the facilitator, once enough have answered to mean something.
    from learners.models import Evaluation

    rated = [e.facilitation for e in Evaluation.objects.filter(facilitator=account, submitted_at__isnull=False,
                                                                enrolment__plan_block__end_date__gte=since) if e.facilitation]
    if len(rated) >= 3:
        avg = round(sum(rated) / len(rated), 1)
        items.append({"key": "feedback", "label": "Learners' rating of the facilitator", "tone": "bad" if avg < 3 else "warn" if avg < 3.8 else "ok",
                      "note": f"{avg} out of 5 from {len(rated)} learners"})
    worst = "bad" if any(i["tone"] == "bad" for i in items) else "warn" if any(i["tone"] == "warn" for i in items) else "ok"
    position = {"bad": "Action required", "warn": "Needs attention", "ok": "In order"}[worst] if items else "No delivery yet"
    return {"items": items, "position": position, "tone": worst if items else "na"}
