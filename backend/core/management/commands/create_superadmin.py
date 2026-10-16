"""Create a super administrator: the System administrator role with full change access to every area of
the hub. The hub itself only lets a system administrator appoint another, so the first one is created here.

    python manage.py create_superadmin "Henry Gidudu" --position "System administrator" --email name@example.com

The password is printed once (and, in the demo, kept in demo-logins.txt like every other demo user)."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from audit.services import record
from core.credentials import new_password
from identity.models import Account, Segment
from identity.users import _save_demo_login, _set_grants, _unique_username


class Command(BaseCommand):
    help = "Create a super administrator (System administrator with change access to every area)."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument("--position", default="System administrator")
        parser.add_argument("--email", default="")

    @transaction.atomic
    def handle(self, name, position, email, **_):
        name = " ".join(name.split())
        if not name:
            raise CommandError("Give the person's name.")
        if Account.objects.filter(display_name__iexact=name, is_active=True).exists():
            raise CommandError(f"{name} already has an account.")
        if email and Account.objects.filter(email__iexact=email).exists():
            raise CommandError(f"{email} already belongs to another user.")
        n = Account.objects.count() + 1
        while Account.objects.filter(reference=f"USR-{n:04d}").exists():
            n += 1
        password = new_password()
        account = Account(reference=f"USR-{n:04d}", username=_unique_username(name), display_name=name, position=position,
                          hub_role="SystemAdministrator", email=email)
        account.set_password(password)
        account.save()
        _set_grants(None, account, {code: ("write", "all") for code in Segment.objects.values_list("code", flat=True)})
        _save_demo_login(account, password)
        record(None, f"User {account.reference} {name} added as super administrator (username {account.username}) "
                     "with change access to every area", account, screen="setup")
        self.stdout.write(f"{name} — super administrator\n  Username: {account.username}\n  Password: {password}\n")
