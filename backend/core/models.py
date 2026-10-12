"""Shared building blocks: row metadata, human references, reference data, the demo clock."""
from django.conf import settings
from django.db import models, transaction


class TrackedModel(models.Model):
    """CreatedAt/CreatedBy/ModifiedAt/ModifiedBy on every table, soft delete, row version."""

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    modified_at = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    is_active = models.BooleanField(default=True)
    row_version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            self.row_version += 1
        super().save(*args, **kwargs)


class RefCounter(models.Model):
    """Gap-free human references (SES-0312, CERT-2026-0412). Row lock serialises issue."""

    prefix = models.CharField(max_length=20, primary_key=True)
    last_value = models.PositiveIntegerField(default=0)


def next_ref(prefix: str, width: int = 4) -> str:
    with transaction.atomic():
        counter, _ = RefCounter.objects.select_for_update().get_or_create(prefix=prefix)
        counter.last_value += 1
        counter.save(update_fields=["last_value"])
        return f"{prefix}-{counter.last_value:0{width}d}"


class ReferencedModel(TrackedModel):
    """A tracked row with a human-readable reference in its own unique column."""

    REF_PREFIX = ""
    REF_WIDTH = 4
    reference = models.CharField(max_length=32, unique=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = next_ref(self.REF_PREFIX, self.REF_WIDTH)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.reference


class Service(models.Model):
    code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=80, unique=True)

    def __str__(self):
        return self.name


class Stream(models.Model):
    """Planner streams. Colours come from the teal ramp and neutral scale, never status colours."""

    code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=80, unique=True)
    colour = models.CharField(max_length=7)
    sort_order = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class Venue(models.Model):
    name = models.CharField(max_length=120, unique=True)
    province = models.CharField(max_length=40, blank=True)
    is_online = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Body(models.Model):
    """Accrediting and registering bodies: AgriSETA, SAATCA, HPCSA, QCTO."""

    code = models.CharField(max_length=12, primary_key=True)
    name = models.CharField(max_length=120)

    def __str__(self):
        return self.name


class PublicHoliday(models.Model):
    day = models.DateField(primary_key=True)
    name = models.CharField(max_length=80)


class DemoClock(models.Model):
    """Single row. In demo mode the business date is read from here so rules fire as seeded."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    today = models.DateField()
