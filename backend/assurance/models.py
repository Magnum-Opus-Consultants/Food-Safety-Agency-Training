import datetime as dt

from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import Body, ReferencedModel
from delivery.models import PlanBlock
from demand.models import Organisation
from identity.models import Account

# An application to an accrediting body (new scope, or the renewal of one held) moves through these steps.
ACC_STEPS = ["Scope confirmed", "Self-evaluation", "Supporting documents", "Application submitted", "Site visit",
             "Accreditation granted"]


class Accreditation(ReferencedModel):
    """An accreditation held with a body for a scope of courses. A renewal is a new row that renews
    the old one, so the history of what was held when stays intact. Delivery of the courses it
    covers stops if it lapses without a renewal."""

    REF_PREFIX = "ACC"
    body = models.ForeignKey(Body, on_delete=models.PROTECT)
    scope = models.CharField(max_length=200)
    number = models.CharField(max_length=60, blank=True)
    granted_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField()
    renews = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="renewed_by")
    courses = models.ManyToManyField("courses.Course", blank=True, related_name="accreditations")
    notes = models.TextField(blank=True)


class AccreditationProject(ReferencedModel):
    """New scope (or a renewal) run as a project through ACC_STEPS, each step with a due date. The
    last step, Accredited, records the accreditation it produced."""

    REF_PREFIX = "ACC-P"
    REF_WIDTH = 2
    body = models.ForeignKey(Body, on_delete=models.PROTECT)
    scope = models.CharField(max_length=200)
    owner = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    target_date = models.DateField()
    step_index = models.PositiveSmallIntegerField(default=0)
    step_due = ArrayField(models.DateField(null=True), default=list, blank=True)
    step_done = ArrayField(models.DateField(null=True), default=list, blank=True)
    step_notes = ArrayField(models.CharField(max_length=400, blank=True), default=list, blank=True)
    state = models.CharField(max_length=10, choices=[(c, c) for c in ("Active", "Accredited", "Withdrawn")], default="Active")
    courses = models.ManyToManyField("courses.Course", blank=True, related_name="accreditation_projects")
    renews = models.ForeignKey(Accreditation, null=True, blank=True, on_delete=models.PROTECT, related_name="renewal_projects")
    result = models.ForeignKey(Accreditation, null=True, blank=True, on_delete=models.PROTECT, related_name="from_projects")
    notes = models.TextField(blank=True)


class Placement(ReferencedModel):
    """University and vet placements: report due twenty days after period end."""

    REF_PREFIX = "PLC"
    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT)
    plan_block = models.ForeignKey(PlanBlock, null=True, blank=True, on_delete=models.PROTECT)
    cohort_label = models.CharField(max_length=120)
    cohort_size = models.PositiveIntegerField()
    period_start = models.DateField()
    period_end = models.DateField()
    report_submitted_at = models.DateTimeField(null=True, blank=True)
    # The placement's checklist: the documents the abattoir needs sent, and its confirmation that it takes
    # the cohort. The files themselves are Documents. (Each student keeps their own WIL book and hands it to
    # the university; the hub does not hold it.)
    abattoir_docs_sent_on = models.DateField(null=True, blank=True)
    abattoir_confirmed_on = models.DateField(null=True, blank=True)

    @property
    def report_due(self):
        return self.period_end + dt.timedelta(days=20)


class Risk(ReferencedModel):
    REF_PREFIX = "TRK"
    REF_WIDTH = 2
    risk = models.CharField(max_length=300)
    cause = models.CharField(max_length=300)
    rating = models.CharField(max_length=6, choices=[(c, c) for c in ("Low", "Medium", "High")])
    escalation_trigger = models.CharField(max_length=300)  # a trigger, not a sentiment
    trigger_breached_at = models.DateTimeField(null=True, blank=True)
    owner = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    position = models.CharField(max_length=200, blank=True)


class Library(models.Model):
    code = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=80)
    holds = models.CharField(max_length=200)
    retention_rule = models.CharField(max_length=120)
    retention_months = models.PositiveIntegerField(default=24)
    owner = models.ForeignKey(Account, null=True, on_delete=models.PROTECT, related_name="+")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]


class Document(ReferencedModel):
    """Files live in object storage; this is the metadata and the hash a verifier checks."""

    REF_PREFIX = "DOC"
    REF_WIDTH = 5
    library = models.ForeignKey(Library, on_delete=models.PROTECT, related_name="documents")
    title = models.CharField(max_length=200)
    entity_type = models.CharField(max_length=60, blank=True)
    entity_ref = models.CharField(max_length=40, blank=True)
    storage_key = models.CharField(max_length=300, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=12, choices=[(c, c) for c in ("Held", "Outstanding", "Archived")], default="Held")
    retain_until = models.DateField(null=True, blank=True)
    archive_ref = models.CharField(max_length=300, blank=True)
