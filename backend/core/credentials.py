"""Demo sign-in details. Passwords are generated, never written into the code, and kept in
demo-logins.txt at the project root (git-ignored). A reset reuses the passwords already in the
file so testers' details do not change under them; delete the file to issue new ones."""
import re
import secrets
import string
from pathlib import Path

from django.conf import settings

LOGINS_FILE = Path(settings.BASE_DIR).parent / "demo-logins.txt"
# No look-alike characters (0/O/o, 1/l/I/i), so a password can be read aloud or retyped from paper.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def username_for(display_name: str) -> str:
    name = re.sub(r"^(Dr|Mr|Ms|Mrs|Prof)\.?\s+", "", display_name.strip())
    return re.sub(r"[^a-z0-9.]+", ".", name.lower().replace(". ", ".")).strip(".")


def new_password() -> str:
    # 14 characters from a 55-symbol alphabet, with at least one digit, upper and lower case letter.
    while True:
        p = "".join(secrets.choice(ALPHABET) for _ in range(14))
        if any(c.isdigit() for c in p) and any(c.isupper() for c in p) and any(c.islower() for c in p):
            return p


def existing_passwords() -> dict[str, str]:
    if not LOGINS_FILE.exists():
        return {}
    found, username = {}, None
    for line in LOGINS_FILE.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"^\s*Username:\s*(\S+)", line):
            username = m.group(1)
        if username and (m := re.search(r"Password:\s*(\S+)", line)):
            found[username] = m.group(1)
            username = None
    return found


def write_logins(rows: list[dict], today: str):
    """rows: name, position, role, username, password, note."""
    lines = [
        "FSA Academy Training Hub — demo sign-in details",
        "=" * 48,
        "",
        "Open http://localhost:3210 and sign in with a username and password below.",
        "The username can also be typed as the person's name, e.g. Louis Visagie.",
        f"Demo business date: {today}. Keep this file private; it is not committed to git.",
        "Delete this file and run `python manage.py reset_demo` to issue new passwords.",
        "",
    ]
    for r in rows:
        lines += [
            f"{r['name']} — {r['role']}",
            f"  {r['position']}",
            f"  Username: {r['username']}",
            f"  Password: {r['password']}",
        ]
        if r.get("note"):
            lines.append(f"  Note: {r['note']}")
        lines.append("")
    lines += [
        "HR and Administration is a service account for the HR Hub link and has no interactive sign-in.",
        "",
    ]
    LOGINS_FILE.write_text("\n".join(lines), encoding="utf-8")
