from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models

from identity.models import Account

FUNCTION_AREAS = [
    ("EnquiryTriage", "Enquiry triage"),
    ("LearnerRecords", "Learner records"),
    ("Filing", "Filing"),
    ("QuoteFollowUp", "Quote follow-up"),
]


class Rotation(models.Model):
    """"Running without her" is held by a rotation. The rotation says who is NEXT;
    the AssignedTo stamp on each item says who DID it, so history survives turnover."""

    function_area = models.CharField(max_length=16, choices=FUNCTION_AREAS)
    member = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="rotations")
    period = DateRangeField()

    class Meta:
        constraints = [
            ExclusionConstraint(
                name="one_member_per_area_at_a_time",
                expressions=[("function_area", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
            )
        ]

    @classmethod
    def on_duty(cls, area: str, day):
        row = cls.objects.filter(function_area=area, period__contains=day).select_related("member").first()
        return row.member if row else None
