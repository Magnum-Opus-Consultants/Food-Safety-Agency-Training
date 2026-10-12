"""The audit trail. Every state-changing action writes one entry, in the same transaction."""
from django.conf import settings
from django.db import models

from core.api_support import stamp


class AuditEntry(models.Model):
    at = models.DateTimeField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    actor_name = models.CharField(max_length=120)
    actor_role = models.CharField(max_length=24, blank=True)
    what = models.CharField(max_length=400)
    entity_type = models.CharField(max_length=60, blank=True)
    entity_ref = models.CharField(max_length=40, blank=True)
    screen = models.CharField(max_length=40, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["screen", "-at"]), models.Index(fields=["entity_type", "entity_ref"])]

    def as_dict(self):
        return {
            "at": stamp(self.at),
            "what": self.what,
            "who": self.actor_name,
            "entityType": self.entity_type,
            "entityRef": self.entity_ref,
        }
