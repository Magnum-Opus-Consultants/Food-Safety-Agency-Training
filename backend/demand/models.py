from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import ReferencedModel, TrackedModel
from courses.models import Course
from identity.models import Account

ENQ_STAGES = ["New", "Responded", "Quoted", "Registered", "Closed — no take-up"]
# What an enquirer asks about (meeting review, "General questions"). "Other" needs a description.
ENQ_TOPICS = [
    ("Accreditation", "Accreditation"),
    ("Costs", "Costs"),
    ("Delivery", "Online or in person"),
    ("Duration", "Duration"),
    ("Quote", "Quote"),
    ("Other", "Other"),
]
TOPIC_LABEL = dict(ENQ_TOPICS)


ENQUIRING_FOR = [("Company", "A company"), ("Individual", "Themselves")]
FOR_LABEL = {"Company": "For a company", "Individual": "For themselves (individual)"}

class Organisation(ReferencedModel):
    REF_PREFIX = "ORG"
    name = models.CharField(max_length=160)
    sector = models.CharField(max_length=60, blank=True)
    relationship = models.CharField(
        max_length=12,
        choices=[(c, c) for c in ("Prospect", "Client", "Partner", "University")],
        default="Prospect",
    )

    class Meta:
        ordering = ["name"]


class Contact(ReferencedModel):
    REF_PREFIX = "CON"
    organisation = models.ForeignKey(Organisation, null=True, blank=True, on_delete=models.PROTECT, related_name="contacts")
    names = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)


class Enquiry(ReferencedModel):
    """A shared queue, not an individual's inbox. Complaints and opportunities are desk triggers."""

    REF_PREFIX = "ENQ"
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT, related_name="enquiries")
    kind = models.CharField(max_length=12, choices=[(c, c) for c in ("Enquiry", "Complaint", "Opportunity")], default="Enquiry")
    # Who the training is for. A company enquiry (for its staff or a group) is quoted and lands on the
    # quotations register. An individual asks for themselves: they may work at a company (recorded as
    # their employer), but they are answered and registered directly, never quoted.
    enquiring_for = models.CharField(max_length=12, choices=ENQUIRING_FOR, default="Individual")
    channel = models.CharField(max_length=12, choices=[(c, c) for c in ("Phone", "Email", "WhatsApp")])
    received_at = models.DateTimeField()
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.PROTECT)
    # Enquiry: the training they meant when it is not a catalogue course. Complaint/opportunity: the details.
    course_interest = models.CharField(max_length=200, blank=True)
    topics = ArrayField(models.CharField(max_length=16, choices=ENQ_TOPICS), default=list, blank=True)
    topic_other = models.CharField(max_length=200, blank=True)
    stage_index = models.PositiveSmallIntegerField(default=0)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [models.CheckConstraint(condition=models.Q(stage_index__lte=4), name="enquiry_stage_range")]

    @property
    def stage(self):
        return ENQ_STAGES[self.stage_index]


class Quotation(ReferencedModel):
    REF_PREFIX = "QTE"
    enquiry = models.ForeignKey(Enquiry, null=True, blank=True, on_delete=models.PROTECT, related_name="quotations")
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT)
    organisation = models.ForeignKey(Organisation, null=True, blank=True, on_delete=models.PROTECT)
    course = models.ForeignKey(Course, on_delete=models.PROTECT)
    basis = models.CharField(max_length=10, choices=[("PerLearner", "Per learner"), ("PerGroup", "Per group")])
    learner_count = models.PositiveIntegerField()
    value_cents = models.BigIntegerField()  # rand in integer cents; never float
    issued_on = models.DateField(null=True, blank=True)
    state = models.CharField(
        max_length=10, choices=[(c, c) for c in ("Draft", "Issued", "Accepted", "Declined", "Lapsed")], default="Draft"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    assigned_to = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    @property
    def follow_up_due(self):
        import datetime as dt

        return self.issued_on + dt.timedelta(days=14) if self.issued_on else None


class QuotationFollowUp(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.PROTECT, related_name="follow_ups")
    at = models.DateTimeField()
    by = models.ForeignKey(Account, null=True, on_delete=models.PROTECT, related_name="+")
    note = models.CharField(max_length=400)
