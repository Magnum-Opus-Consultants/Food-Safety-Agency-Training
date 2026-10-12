from django.db import models

from core.models import Body, Service, Stream, TrackedModel

ENTRY_GATES = [
    ("PrerequisiteAndGrade10", "Prerequisite test ≥ 50% and Grade 10"),
    ("PriorCourse", "Prior course competent"),
    ("Documented", "Documented requirement"),
    ("None", "None"),
]


class Course(TrackedModel):
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=160)
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    stream = models.ForeignKey(Stream, on_delete=models.PROTECT)
    pack_type = models.CharField(max_length=60)
    duration_days = models.PositiveSmallIntegerField()
    delivery_mode = models.CharField(max_length=60)
    entry_gate = models.CharField(max_length=24, choices=ENTRY_GATES)
    entry_requirement = models.CharField(max_length=160)
    prior_course = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    # Which registration a facilitator must hold to deliver it. Not yet specified by FSA (open item).
    required_registration_type = models.CharField(max_length=120, blank=True)
    is_accredited = models.BooleanField(default=False)
    accreditation_body = models.ForeignKey(Body, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.title
