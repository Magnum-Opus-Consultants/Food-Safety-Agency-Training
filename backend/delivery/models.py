from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import ReferencedModel, Stream, TrackedModel, Venue
from courses.models import Course
from identity.models import Account

DELIVERY_MODES = ["Contact", "Contact and workplace", "Workplace", "Online", "Blended"]
# How an intake meets: every weekday of a block course, set days each week (e.g. Tuesday and
# Thursday for two months), or a single day. Each meeting is a session with its own register.
SCHEDULES = [("Block", "Every weekday, start to end"), ("Weekly", "Set days each week"), ("Single", "One day")]
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class PlanBlock(ReferencedModel):
    """A planned delivery. Fill, load, warnings and clashes are derived, never stored."""

    REF_PREFIX = "PLN"
    REF_WIDTH = 2
    course = models.ForeignKey(Course, on_delete=models.PROTECT)
    stream = models.ForeignKey(Stream, on_delete=models.PROTECT)
    facilitator = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="plan_blocks")
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT)
    delivery_mode = models.CharField(max_length=24, choices=[(m, m) for m in DELIVERY_MODES])
    intake_cadence = models.CharField(
        max_length=10, choices=[(c, c) for c in ("Monthly", "Quarterly", "AdHoc")], default="AdHoc"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    capacity = models.PositiveIntegerField()
    practical_hours = models.PositiveIntegerField(default=0)
    schedule = models.CharField(max_length=8, choices=SCHEDULES, default="Block")
    weekdays = ArrayField(models.PositiveSmallIntegerField(), default=list, blank=True)  # 0 Monday … 6 Sunday
    starts_at = models.TimeField(null=True, blank=True)
    ends_at = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    state = models.CharField(
        max_length=10, choices=[(c, c) for c in ("Draft", "Confirmed", "Cancelled")], default="Draft"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="block_dates_ordered"),
        ]


    @property
    def seats_booked(self) -> int:
        """Derived, never stored: the active enrolments on this intake. A seat is reserved when the
        learner is registered, the first stage. Querysets that list many blocks annotate `booked`
        to avoid a count per row."""
        if "booked" in self.__dict__:
            return self.__dict__["booked"]
        return self.enrolments.filter(is_active=True).count()


class Session(ReferencedModel):
    REF_PREFIX = "SES"
    """One meeting of an intake, with its own register. An intake planned before meetings were
    scheduled has a single session with no day: one register for the whole intake."""

    plan_block = models.ForeignKey(PlanBlock, on_delete=models.PROTECT, related_name="sessions")
    day = models.DateField(null=True, blank=True)
    sequence = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["plan_block__start_date", "day", "reference"]

    @property
    def first_day(self):
        return self.day or self.plan_block.start_date

    @property
    def last_day(self):
        return self.day or self.plan_block.end_date


class AttendanceRegister(models.Model):
    """The existence of this row IS the lock. Register state is derived from it."""

    session = models.OneToOneField(Session, primary_key=True, on_delete=models.PROTECT, related_name="register")
    locked_at = models.DateTimeField()
    locked_by = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")


class Attendance(models.Model):
    """Insert-only (enforced by database trigger). A correction is a new row that supersedes."""

    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name="attendance")
    learner = models.ForeignKey("learners.Learner", on_delete=models.PROTECT, related_name="attendance")
    present = models.BooleanField()
    captured_at = models.DateTimeField()
    captured_by = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    supersedes = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="superseded_by")
    correction_reason = models.CharField(max_length=300, blank=True)
    # A learner added to a register after it was locked (confirmed late, missed at capture). The lock
    # stays; the addition is a new row with its reason, never an edit.
    late_entry = models.BooleanField(default=False)

    class Meta:
        ordering = ["captured_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "learner"], condition=models.Q(supersedes__isnull=True), name="attendance_original_once"
            ),
            models.CheckConstraint(
                condition=models.Q(supersedes__isnull=True, correction_reason="", late_entry=False)
                | (models.Q(supersedes__isnull=False) & ~models.Q(correction_reason=""))
                | (models.Q(supersedes__isnull=True, late_entry=True) & ~models.Q(correction_reason="")),
                name="correction_needs_reason",
            ),
        ]
