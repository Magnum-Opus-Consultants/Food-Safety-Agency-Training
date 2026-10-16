"""Accounts, segment access and facilitator registrations.

Rules carried from 04-roles-and-access.md:
  1. Accreditation drives access: an account is suspended the day its registration lapses.
  2. Expiry warns at ninety days (derived, never stored).
  4. Every role or segment change is audited.
  6. The client is not the gate: can() is checked server-side on every endpoint.
"""
import datetime as dt

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models

from core import clock
from core.models import Body, ReferencedModel, TrackedModel

HUB_ROLES = [
    ("TrainingManager", "Training manager"),
    ("Facilitator", "Facilitator"),
    ("Assessor", "Assessor"),
    ("Moderator", "Moderator"),
    ("EnquiryHandler", "Enquiry handler"),
    ("Learner", "Learner"),
    ("Director", "Director"),
    ("SystemAdministrator", "System administrator"),
]
ROLE_LABEL = dict(HUB_ROLES)

# Roles that read every register (04-roles-and-access.md: "Every register, read only").
READ_ALL_ROLES = {"TrainingManager", "Director", "SystemAdministrator"}
# The audit trail (who changed what, and when) is read only by directors and system administrators.
AUDIT_ROLES = {"Director", "SystemAdministrator"}
# The head of department desk is the training manager's (the head of department), and directors and
# system administrators, who read everything. Other staff work their own streams, not the desk.
DESK_ROLES = {"TrainingManager", "Director", "SystemAdministrator"}
# The department picture is open to every staff account: on login every role lands there first.
DEPARTMENT_SEGMENTS = {"overview"}


class AccountManager(BaseUserManager):
    def create_user(self, username, display_name, password=None, **extra):
        account = self.model(username=username.lower(), display_name=display_name, **extra)
        account.set_password(password) if password else account.set_unusable_password()
        account.save(using=self._db)
        return account

    def create_superuser(self, username, display_name="Administrator", password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, hub_role="SystemAdministrator", position="Platform administrator")
        return self.create_user(reference, display_name, password, **extra)


class Account(AbstractBaseUser, PermissionsMixin, TrackedModel):
    reference = models.CharField(max_length=16, unique=True)
    username = models.CharField(max_length=60, unique=True)
    display_name = models.CharField(max_length=120)
    position = models.CharField(max_length=160)
    reports_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reports")
    reports_to_label = models.CharField(max_length=120, blank=True)
    hub_role = models.CharField(max_length=24, choices=HUB_ROLES)
    email = models.EmailField(blank=True)
    idp_subject = models.CharField(max_length=200, null=True, blank=True, unique=True)
    hr_person_id = models.BigIntegerField(null=True, blank=True, unique=True)
    is_service_account = models.BooleanField(default=False)
    state = models.CharField(max_length=10, choices=[("Active", "Active"), ("Suspended", "Suspended")], default="Active")
    suspended_reason = models.CharField(max_length=240, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    # The provinces a facilitator delivers in. Planning prefers them for intakes there; an intake
    # elsewhere is a warning, not a block (a facilitator may travel).
    regions = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["display_name", "reference"]
    objects = AccountManager()

    class Meta:
        ordering = ["reference"]

    def __str__(self):
        return self.display_name

    # --- registrations ------------------------------------------------------------
    def current_registration(self):
        return self.registrations.filter(is_active=True).order_by("-expires_on").first()

    def registration_standing(self, on: dt.date | None = None) -> str | None:
        reg = self.current_registration()
        if not reg:
            return None
        return reg.standing(on)

    @property
    def is_suspended(self) -> bool:
        """Suspended in the record, or lapsed today even if the daily job has not run yet."""
        return self.state == "Suspended" or self.registration_standing() == "Lapsed"

    def display_state(self):
        reg = self.current_registration()
        standing = reg.standing() if reg else None
        if self.is_suspended:
            return "Suspended", "bad"
        if standing == "Expiring":
            return f"Expires {reg.expires_on.isoformat()}", "warn"
        return "Active", "ok"

    # --- access ---------------------------------------------------------------------
    def segment_rows(self):
        if not hasattr(self, "_segment_cache"):
            self._segment_cache = {s.segment_id: s for s in self.segments.all()}
        return self._segment_cache

    @property
    def can_see_desk(self) -> bool:
        return self.hub_role in DESK_ROLES

    @property
    def can_see_audit(self) -> bool:
        return self.hub_role in AUDIT_ROLES

    def can(self, segment: str, write: bool = False) -> bool:
        if not self.is_active or self.is_suspended:
            return False
        if segment in DEPARTMENT_SEGMENTS and not write:
            return True
        row = self.segment_rows().get(segment)
        if write:
            return bool(row and row.access == "write")
        return bool(row) or self.hub_role in READ_ALL_ROLES

    def scope(self, segment: str) -> str:
        """'own' limits a facilitator to their own sessions; everyone else sees 'all'."""
        row = self.segment_rows().get(segment)
        if row and row.scope == "own" and self.hub_role not in READ_ALL_ROLES:
            return "own"
        return "all"

    def readable_segments(self):
        from identity.models import Segment

        return [s for s in Segment.objects.values_list("code", flat=True) if self.can(s)]


class Segment(models.Model):
    code = models.CharField(max_length=24, primary_key=True)
    name = models.CharField(max_length=120)

    def __str__(self):
        return self.name


class AccountSegment(models.Model):
    """Access is granted by segment, not by screen. Segments are rows, not a flag column."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="segments")
    segment = models.ForeignKey(Segment, on_delete=models.PROTECT)
    access = models.CharField(max_length=5, choices=[("read", "read"), ("write", "write")])
    scope = models.CharField(max_length=3, choices=[("all", "all"), ("own", "own")], default="all")
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "segment"], name="account_segment_once")]


class FacilitatorRegistration(TrackedModel):
    """Drives planner warnings, the scheduling hard block and account suspension."""

    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="registrations")
    registration_type = models.CharField(max_length=120)
    body = models.ForeignKey(Body, on_delete=models.PROTECT)
    registration_no = models.CharField(max_length=60, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField()

    class Meta:
        ordering = ["expires_on"]

    def standing(self, on: dt.date | None = None) -> str:
        on = on or clock.today()
        if self.expires_on < on:
            return "Lapsed"
        if self.expires_on <= on + dt.timedelta(days=90):
            return "Expiring"
        return "Current"
