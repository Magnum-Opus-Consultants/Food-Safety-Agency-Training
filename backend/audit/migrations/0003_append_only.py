"""The audit trail is append-only for everyone, including the application."""
from django.db import migrations

SQL = r"""
CREATE FUNCTION audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_append_only: the audit trail cannot be edited or deleted' USING ERRCODE = 'P0409';
END $$;
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit_auditentry
  FOR EACH ROW EXECUTE FUNCTION audit_append_only();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS audit_append_only ON audit_auditentry;
DROP FUNCTION IF EXISTS audit_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0002_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
