import datetime as dt

from django.db import models

from core.models import Body, Service, Stream, TrackedModel

ENTRY_GATES = [
    ("PrerequisiteAndGrade10", "Prerequisite test and Grade 10"),
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

    @property
    def reference(self):
        """The course code is its reference: audit entries for a course are filed under it."""
        return self.code


class CourseRequirement(models.Model):
    """One version of a course's minimum prerequisites. Versions are never edited or deleted (a
    database trigger refuses it): a change is a new version with the date it takes effect. An intake
    is judged by the version in force on its start date, so learners already registered on an intake
    keep the requirement they registered under, and a change applies from the next intake."""

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="requirements")
    version = models.PositiveSmallIntegerField()
    effective_from = models.DateField()
    kind = models.CharField(max_length=24, choices=ENTRY_GATES)
    pass_mark = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    prior_course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    description = models.CharField(max_length=200, blank=True)
    reason = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("identity.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["course", "effective_from", "version"]
        constraints = [
            models.UniqueConstraint(fields=["course", "version"], name="one_requirement_version_number"),
            models.CheckConstraint(condition=~models.Q(kind="PrerequisiteAndGrade10") | models.Q(pass_mark__isnull=False),
                                   name="test_requirement_has_pass_mark"),
            models.CheckConstraint(condition=~models.Q(kind="PriorCourse") | models.Q(prior_course__isnull=False),
                                   name="prior_course_requirement_names_course"),
        ]

    @property
    def gated(self) -> bool:
        return self.kind == "PrerequisiteAndGrade10"

    @property
    def label(self) -> str:
        if self.kind == "PrerequisiteAndGrade10":
            return f"Prerequisite test ≥ {self.pass_mark.normalize():f}% and Grade 10"
        if self.kind == "PriorCourse":
            return f"{self.prior_course.title.split(' — ')[0]} competent"
        if self.kind == "Documented":
            return self.description
        return "None"


EARLIEST = dt.date(2000, 1, 1)
