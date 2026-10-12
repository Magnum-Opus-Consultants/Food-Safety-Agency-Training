"""Sign-in by username and password: add Account.username and make it the login field."""
from django.db import migrations, models


def fill_usernames(apps, schema_editor):
    Account = apps.get_model("identity", "Account")
    for account in Account.objects.filter(username__isnull=True):
        account.username = account.reference.lower()
        account.save(update_fields=["username"])


class Migration(migrations.Migration):
    dependencies = [("identity", "0001_initial")]
    operations = [
        migrations.AddField("account", "username", models.CharField(max_length=60, null=True)),
        migrations.RunPython(fill_usernames, migrations.RunPython.noop),
        migrations.AlterField("account", "username", models.CharField(max_length=60, unique=True)),
    ]
