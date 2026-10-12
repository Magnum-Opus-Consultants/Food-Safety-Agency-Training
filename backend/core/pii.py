"""Identity numbers under POPIA.

An SA ID or passport number is never stored in the clear and never returned by the API:
  * the number is encrypted (Fernet: AES-128-CBC + HMAC-SHA256) into Learner.id_number_cipher;
  * a keyed hash (HMAC-SHA256) goes into Learner.id_number_hmac, unique, so the same person is
    found again without anyone being able to read or guess the number from the index;
  * only the last four digits are kept for display, so staff can confirm they have the right person.

Keys come from the environment (FSA_PII_ENCRYPTION_KEY, FSA_PII_INDEX_KEY). In development they are
derived from the Django secret key; production refuses to start without real keys (see settings).
"""
import base64
import datetime as dt
import hashlib
import hmac
import re
from dataclasses import dataclass

from cryptography.fernet import Fernet
from django.conf import settings

ID_TYPES = ("SAID", "Passport")


@dataclass
class IdentityNumber:
    id_type: str
    number: str  # normalised

    @property
    def last4(self) -> str:
        return self.number[-4:]


def _fernet() -> Fernet:
    return Fernet(settings.FSA_PII_ENCRYPTION_KEY)


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt(token: bytes) -> str:
    return _fernet().decrypt(bytes(token)).decode()


def blind_index(ident: IdentityNumber) -> bytes:
    key = base64.urlsafe_b64decode(settings.FSA_PII_INDEX_KEY)
    return hmac.new(key, f"{ident.id_type}:{ident.number}".encode(), hashlib.sha256).digest()


def mask(id_type: str, last4: str) -> str:
    if not last4:
        return ""
    return ("SA ID " if id_type == "SAID" else "Passport ") + "•••• " + last4


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def sa_id_problem(number: str) -> str | None:
    """None if the number is a well-formed South African ID number, otherwise what is wrong."""
    if not re.fullmatch(r"\d{13}", number):
        return "an SA ID number has 13 digits"
    yy, mm, dd = int(number[0:2]), int(number[2:4]), int(number[4:6])
    today = dt.date.today()
    century = 2000 if 2000 + yy <= today.year else 1900
    try:
        dt.date(century + yy, mm, dd)
    except ValueError:
        return f"the date of birth {number[0:6]} is not a real date"
    if number[10] not in "012":
        return "the citizenship digit (11th) must be 0, 1 or 2"
    if not luhn_ok(number):
        return "the check digit does not match; check for a mistyped digit"
    return None


def parse(id_type: str, raw: str) -> tuple[IdentityNumber | None, str | None]:
    """Normalise and validate. Returns (identity, None) or (None, problem)."""
    raw = (raw or "").strip()
    if not raw:
        return None, None
    if id_type not in ID_TYPES:
        return None, "choose SA ID or passport"
    if id_type == "SAID":
        number = re.sub(r"[\s-]", "", raw)
        problem = sa_id_problem(number)
        return (None, problem) if problem else (IdentityNumber("SAID", number), None)
    number = re.sub(r"[\s-]", "", raw).upper()
    if not re.fullmatch(r"[A-Z0-9]{6,12}", number):
        return None, "a passport number is 6 to 12 letters and digits"
    return IdentityNumber("Passport", number), None
