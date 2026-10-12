"""Rule 3 backstop: attendance is insert-only and locks with its register.

The API refuses first; these triggers refuse again if any code path ever tries.
"""
from django.db import migrations

SQL = r"""
CREATE FUNCTION delivery_attendance_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE locked boolean;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'register_locked: an attendance record is never edited; capture a correction instead'
      USING ERRCODE = 'P0409';
  END IF;
  SELECT EXISTS (SELECT 1 FROM delivery_attendanceregister r WHERE r.session_id = NEW.session_id) INTO locked;
  IF locked AND NEW.supersedes_id IS NULL THEN
    RAISE EXCEPTION 'register_locked: this register is locked; a change after capture is a correction'
      USING ERRCODE = 'P0409';
  END IF;
  IF NEW.supersedes_id IS NOT NULL AND NOT locked THEN
    RAISE EXCEPTION 'register_not_locked: a correction applies only to a locked register' USING ERRCODE = 'P0409';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER attendance_guard BEFORE INSERT OR UPDATE OR DELETE ON delivery_attendance
  FOR EACH ROW EXECUTE FUNCTION delivery_attendance_guard();

CREATE FUNCTION delivery_register_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'register_locked: a locked register cannot be unlocked or changed' USING ERRCODE = 'P0409';
END $$;
CREATE TRIGGER register_immutable BEFORE UPDATE OR DELETE ON delivery_attendanceregister
  FOR EACH ROW EXECUTE FUNCTION delivery_register_immutable();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS attendance_guard ON delivery_attendance;
DROP FUNCTION IF EXISTS delivery_attendance_guard();
DROP TRIGGER IF EXISTS register_immutable ON delivery_attendanceregister;
DROP FUNCTION IF EXISTS delivery_register_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("delivery", "0002_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
