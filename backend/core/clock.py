"""The business clock. Every SLA, expiry and deadline rule reads today() from here.

It is the real date. In demo mode the training manager can move it temporarily (the arrows on
the date pill) to watch a trigger fire, and return it to today; FSA_DEMO_TODAY pins a start date
(the automated tests pin 2026-09-09, the prototype's date).
"""
import datetime as dt

from django.conf import settings
from django.utils import timezone


def today() -> dt.date:
    if settings.DEMO_MODE:
        from core.models import DemoClock

        row = DemoClock.objects.filter(pk=1).first()
        if row:
            return row.today
        if settings.DEMO_TODAY:
            return dt.date.fromisoformat(settings.DEMO_TODAY)
    return timezone.localdate()


def is_moved() -> bool:
    """True while the demo clock is set away from the real date."""
    return today() != timezone.localdate()


def now() -> dt.datetime:
    """The business date combined with the real local time of day."""
    real = timezone.localtime()
    return real.replace(year=(d := today()).year, month=d.month, day=d.day)


def local_date(value: dt.datetime) -> dt.date:
    return timezone.localtime(value).date()


def working_days_since(value: dt.datetime | dt.date) -> int:
    """Working days strictly after the given moment, up to and including today.

    Weekends and South African public holidays are excluded.
    """
    from core.models import PublicHoliday

    start = value if isinstance(value, dt.date) and not isinstance(value, dt.datetime) else local_date(value)
    end = today()
    if end <= start:
        return 0
    holidays = set(PublicHoliday.objects.filter(day__gt=start, day__lte=end).values_list("day", flat=True))
    count, day = 0, start + dt.timedelta(days=1)
    while day <= end:
        if day.isoweekday() < 6 and day not in holidays:
            count += 1
        day += dt.timedelta(days=1)
    return count


def working_days_between(start: dt.datetime, end: dt.datetime) -> int:
    """Working days strictly after `start` up to and including `end` (both moments)."""
    from core.models import PublicHoliday

    a, b = local_date(start), local_date(end)
    if b <= a:
        return 0
    holidays = set(PublicHoliday.objects.filter(day__gt=a, day__lte=b).values_list("day", flat=True))
    count, day = 0, a + dt.timedelta(days=1)
    while day <= b:
        if day.isoweekday() < 6 and day not in holidays:
            count += 1
        day += dt.timedelta(days=1)
    return count


def week_of(day: dt.date) -> tuple[dt.date, dt.date]:
    monday = day - dt.timedelta(days=day.weekday())
    return monday, monday + dt.timedelta(days=6)
