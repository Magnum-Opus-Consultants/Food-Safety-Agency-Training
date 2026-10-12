from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from audit.services import record
from core import clock
from core.credentials import LOGINS_FILE, new_password, write_logins
from identity.models import Account


class Command(BaseCommand):
    help = "Issue new passwords to every demo account and rewrite demo-logins.txt. Leaves all other data untouched."

    def handle(self, *args, **opts):
        if not settings.DEMO_MODE:
            raise CommandError("issue_demo_passwords only runs with FSA_DEMO_MODE=true")
        rows = []
        with transaction.atomic():
            for a in Account.objects.filter(is_active=True, is_service_account=False).order_by("reference"):
                password = new_password()
                a.set_password(password)
                a.save(update_fields=["password", "row_version", "modified_at"])
                note = "Suspended — sign-in is refused and says why." if a.is_suspended else ""
                rows.append({"name": a.display_name, "position": a.position, "role": a.get_hub_role_display(),
                             "username": a.username, "password": password, "note": note})
            record(None, "Demo passwords reissued for every account", screen="system")
        write_logins(rows, clock.today().isoformat())
        self.stdout.write(self.style.SUCCESS(f"New passwords for {len(rows)} accounts written to {LOGINS_FILE}"))
