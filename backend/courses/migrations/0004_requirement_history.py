"""Version 1 of every course's requirement, taken from the catalogue, and the guard that keeps the
requirement history permanent: versions can be added, never edited or deleted."""
import datetime as dt
from decimal import Decimal

from django.db import migrations

SQL = r"""
CREATE FUNCTION course_requirement_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'course_requirement_append_only: a requirement version cannot be edited or deleted; add a new version' USING ERRCODE = 'P0409';
END $$;
CREATE TRIGGER course_requirement_append_only BEFORE UPDATE OR DELETE ON courses_courserequirement
  FOR EACH ROW EXECUTE FUNCTION course_requirement_append_only();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS course_requirement_append_only ON courses_courserequirement;
DROP FUNCTION IF EXISTS course_requirement_append_only();
"""


def first_versions(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    Requirement = apps.get_model("courses", "CourseRequirement")
    for c in Course.objects.all():
        Requirement.objects.create(
            course=c, version=1, effective_from=dt.date(2000, 1, 1), kind=c.entry_gate,
            pass_mark=Decimal("50") if c.entry_gate == "PrerequisiteAndGrade10" else None,
            prior_course_id=c.prior_course_id,
            description=c.entry_requirement if c.entry_gate == "Documented" else "",
            reason="Requirement in the course catalogue when the Training Hub went live",
        )


class Migration(migrations.Migration):
    dependencies = [("courses", "0003_course_requirement_versions")]
    operations = [
        migrations.RunPython(first_versions, migrations.RunPython.noop),
        migrations.RunSQL(SQL, REVERSE),
    ]
