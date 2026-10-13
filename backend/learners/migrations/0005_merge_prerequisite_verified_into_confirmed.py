from django.db import migrations, models
from django.utils import timezone

# Old stages: 0 Applied, 1 Prerequisite verified, 2 Registered, 3 In training, 4 Completed.
# New stages: 0 Registered, 1 Confirmed (prerequisites met), 2 In training, 3 Completed.
OLD = ["Applied", "Prerequisite verified", "Registered", "In training", "Completed"]
NEW = ["Registered", "Confirmed", "In training", "Completed"]
REMAP = {0: 0, 1: 1, 2: 1, 3: 2, 4: 3}


def renumber(apps, schema_editor):
    """Prerequisite verified and the old Registered were one step in practice: meeting the minimum
    prerequisites confirms the place. Enrolments are renumbered; one audit entry records the change."""
    Enrolment = apps.get_model("learners", "Enrolment")
    AuditEntry = apps.get_model("audit", "AuditEntry")
    moved = {}
    for e in Enrolment.objects.all().order_by("pk"):
        new = REMAP[e.stage_index]
        if new != e.stage_index:
            key = f"{OLD[e.stage_index]} → {NEW[new]}"
            moved[key] = moved.get(key, 0) + 1
            e.stage_index = new
            e.save(update_fields=["stage_index"])
    AuditEntry.objects.create(
        at=timezone.now(), actor=None, actor_name="System", actor_role="System",
        what="Enrolment stages simplified to Registered, Confirmed, In training, Completed; enrolments renumbered"
             + (" — " + "; ".join(f"{n} {k}" for k, n in moved.items()) if moved else ""),
        entity_type="learners.enrolment", entity_ref="", screen="system",
        before={"stages": OLD}, after={"stages": NEW},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0003_append_only"),
        ("learners", "0004_derived_seats_and_identity"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="enrolment", name="enrolment_stage_range"),
        migrations.RunPython(renumber, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="enrolment",
            constraint=models.CheckConstraint(condition=models.Q(stage_index__lte=3), name="enrolment_stage_range"),
        ),
    ]
