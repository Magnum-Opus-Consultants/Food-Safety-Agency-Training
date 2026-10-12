"""Rule 4 backstop: no certificate row can exist without a Competent moderation.

The certificate's moderation foreign key is required; this trigger also refuses a
not-yet-competent moderation. Moderation records are immutable once written.
"""
from django.db import migrations

SQL = r"""
CREATE FUNCTION learners_certificate_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m_outcome text;
BEGIN
  SELECT outcome INTO m_outcome FROM learners_moderation WHERE id = NEW.moderation_id;
  IF m_outcome IS DISTINCT FROM 'Competent' THEN
    RAISE EXCEPTION 'not_moderated: a certificate requires a moderated competent result' USING ERRCODE = 'P0409';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER certificate_guard BEFORE INSERT OR UPDATE OF moderation_id ON learners_certificate
  FOR EACH ROW EXECUTE FUNCTION learners_certificate_guard();

CREATE FUNCTION learners_moderation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'moderation_final: a moderation record is never edited or removed' USING ERRCODE = 'P0409';
END $$;
CREATE TRIGGER moderation_immutable BEFORE UPDATE OR DELETE ON learners_moderation
  FOR EACH ROW EXECUTE FUNCTION learners_moderation_immutable();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS certificate_guard ON learners_certificate;
DROP FUNCTION IF EXISTS learners_certificate_guard();
DROP TRIGGER IF EXISTS moderation_immutable ON learners_moderation;
DROP FUNCTION IF EXISTS learners_moderation_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("learners", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
