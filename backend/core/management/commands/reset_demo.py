from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.credentials import LOGINS_FILE
from core.seed import seed, truncate_all


class Command(BaseCommand):
    help = "Wipe the demo database and reload the prototype data (demo mode only)."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")

    def handle(self, *args, **opts):
        if not settings.DEMO_MODE:
            raise CommandError("reset_demo only runs with FSA_DEMO_MODE=true")
        if not opts["yes"]:
            answer = input("This deletes everything the department has captured in the demo. Type 'reset' to continue: ")
            if answer.strip() != "reset":
                raise CommandError("Cancelled")
        truncate_all()
        seed(write_file=True)
        self.stdout.write(self.style.SUCCESS(
            f"Demo data loaded. Business date {settings.DEMO_TODAY or 'today (real date)'}."))
        self.stdout.write(f"Sign-in details written to {LOGINS_FILE}")
