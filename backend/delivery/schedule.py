"""The meetings of an intake, worked out from its schedule.

Block: every weekday from start to end. Weekly: the chosen days of the week between start and end.
Single: the start date only. Public holidays are skipped. Each meeting becomes a session with its own
register; an intake that has started keeps its sessions as they are."""

import datetime as dt

from core.models import PublicHoliday


def meeting_dates(schedule: str, weekdays: list[int], start: dt.date, end: dt.date) -> list[dt.date]:
    if schedule == "Single":
        return [start]
    holidays = set(PublicHoliday.objects.filter(day__gte=start, day__lte=end).values_list("day", flat=True))
    days = set(weekdays) if schedule == "Weekly" else {0, 1, 2, 3, 4}
    out, day = [], start
    while day <= end:
        if day.weekday() in days and day not in holidays:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def sync_sessions(block, actor):
    """Make the intake's active sessions match its schedule: keep meetings that still fall on a
    meeting date, retire the rest (none has a register: the intake has not started), add new ones."""
    from delivery.models import Session

    wanted = meeting_dates(block.schedule, block.weekdays, block.start_date, block.end_date)
    current = list(Session.objects.filter(plan_block=block, is_active=True))
    keep = {s.day: s for s in current if s.day in wanted}
    for s in current:
        if s.day not in keep or keep[s.day].pk != s.pk:
            s.is_active, s.modified_by = False, actor
            s.save(update_fields=["is_active", "modified_by", "modified_at"])
    for n, day in enumerate(wanted, start=1):
        s = keep.get(day) or Session(plan_block=block, day=day, created_by=actor)
        s.sequence, s.is_active, s.modified_by = n, True, actor
        s.save()
    return wanted
