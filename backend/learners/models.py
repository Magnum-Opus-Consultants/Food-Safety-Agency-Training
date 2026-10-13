from django.db import models

from core.models import ReferencedModel
from courses.models import Course
from delivery.models import PlanBlock, Session
from demand.models import Contact, Organisation, Quotation
from identity.models import Account

# Registering the learner is the first stage and reserves their seat on the intake. Confirmed means
# the minimum prerequisites are met and verified: from then on the learner is on the class list.
ENR_STAGES = ["Registered", "Confirmed", "In training", "Completed"]
CONFIRMED, IN_TRAINING, COMPLETED = 1, 2, 3


class Learner(ReferencedModel):
    """Identity is shared with the HR directory: an FSA employee links by hr_person_id."""

    REF_PREFIX = "LRN"
    hr_person_id = models.BigIntegerField(null=True, blank=True, unique=True)
    names = models.CharField(max_length=120)
    # Student number from the university, or staff number from a corporate client.
    external_ref = models.CharField(max_length=40, blank=True)
    learner_type = models.CharField(
        max_length=12, choices=[(c, c) for c in ("Public", "Corporate", "University", "Employee")]
    )
    organisation = models.ForeignKey(Organisation, null=True, blank=True, on_delete=models.PROTECT)
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.PROTECT)
    # POPIA (core/pii.py): the SA ID or passport number is stored only as ciphertext, plus a keyed
    # hash that finds the same person again, plus the last four digits for display. Never returned.
    id_type = models.CharField(max_length=8, blank=True, choices=[("SAID", "SA ID"), ("Passport", "Passport")])
    id_number_cipher = models.BinaryField(null=True, blank=True, editable=False)
    id_number_hmac = models.BinaryField(null=True, blank=True, unique=True, editable=False)
    id_last4 = models.CharField(max_length=4, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    consent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["names"]
        constraints = [
            models.UniqueConstraint(fields=["organisation", "external_ref"], condition=~models.Q(external_ref=""),
                                    name="one_learner_per_student_number"),
        ]


class Enrolment(ReferencedModel):
    REF_PREFIX = "ENR"
    learner = models.ForeignKey(Learner, on_delete=models.PROTECT, related_name="enrolments")
    course = models.ForeignKey(Course, on_delete=models.PROTECT)
    plan_block = models.ForeignKey(PlanBlock, null=True, blank=True, on_delete=models.PROTECT, related_name="enrolments")
    quotation = models.ForeignKey(Quotation, null=True, blank=True, on_delete=models.PROTECT, related_name="enrolments")
    enquiry = models.ForeignKey("demand.Enquiry", null=True, blank=True, on_delete=models.PROTECT, related_name="enrolments")
    basis = models.CharField(
        max_length=20, choices=[(c, c) for c in ("PerLearner", "PerGroup", "UniversityAgreement", "Employee")]
    )
    stage_index = models.PositiveSmallIntegerField(default=0)
    prerequisite_result = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    grade10_evidence_held = models.BooleanField(default=False)
    development_plan_id = models.BigIntegerField(null=True, blank=True)
    assigned_to = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["reference"]
        constraints = [
            models.CheckConstraint(condition=models.Q(stage_index__lte=3), name="enrolment_stage_range"),
            models.UniqueConstraint(fields=["learner", "plan_block"], condition=models.Q(is_active=True, plan_block__isnull=False),
                                    name="one_enrolment_per_learner_per_intake"),
        ]

    @property
    def stage(self):
        return ENR_STAGES[self.stage_index]


class Result(ReferencedModel):
    REF_PREFIX = "RES"
    enrolment = models.ForeignKey(Enrolment, on_delete=models.PROTECT, related_name="results")
    session = models.ForeignKey(Session, null=True, blank=True, on_delete=models.PROTECT, related_name="results")
    assessed_by = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    assessed_at = models.DateTimeField()
    mark = models.DecimalField(max_digits=5, decimal_places=2)
    outcome = models.CharField(max_length=16, choices=[("Competent", "Competent"), ("NotYetCompetent", "Not yet competent")])
    remediation_plan = models.TextField(blank=True)

    class Meta:
        ordering = ["reference"]


class Moderation(models.Model):
    """Assessed by the official, moderated by the manager, in that order."""

    result = models.OneToOneField(Result, on_delete=models.PROTECT, related_name="moderation")
    moderated_by = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    moderated_at = models.DateTimeField()
    outcome = models.CharField(max_length=16, choices=[("Competent", "Competent"), ("NotYetCompetent", "Not yet competent")])
    notes = models.TextField(blank=True)


class Certificate(models.Model):
    """Rule 4: a certificate row cannot exist without a Competent moderation (API + DB trigger)."""

    reference = models.CharField(max_length=32, unique=True)
    moderation = models.OneToOneField(Moderation, on_delete=models.PROTECT, related_name="certificate")
    issued_at = models.DateTimeField()
    issued_by = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    verification_code = models.CharField(max_length=24, unique=True)
    document = models.ForeignKey("assurance.Document", null=True, blank=True, on_delete=models.PROTECT)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-issued_at"]
