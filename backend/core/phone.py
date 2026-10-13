"""Phone numbers with a country code. Learners and clients come from South Africa and its
neighbours (Namibia especially), so a number is always stored in international form:
"+264 812345678" — the country code, a space, then the national number without its leading 0.

A number typed the local South African way ("082 555 0101") is read as +27, because that is how
the department has always captured them.
"""
import re

# The countries offered first in the selector; any other code is still accepted.
COUNTRIES = [
    ("ZA", "South Africa", "27"),
    ("NA", "Namibia", "264"),
    ("BW", "Botswana", "267"),
    ("LS", "Lesotho", "266"),
    ("SZ", "Eswatini", "268"),
    ("ZW", "Zimbabwe", "263"),
    ("MZ", "Mozambique", "258"),
    ("ZM", "Zambia", "260"),
    ("MW", "Malawi", "265"),
    ("AO", "Angola", "244"),
    ("GB", "United Kingdom", "44"),
]
DEFAULT_CODE = "27"
_KNOWN = sorted({c for _, _, c in COUNTRIES}, key=len, reverse=True)


def normalise(raw: str) -> tuple[str, str | None]:
    """Return (stored value, None) or ("", what is wrong). Blank stays blank."""
    raw = (raw or "").strip()
    if not raw:
        return "", None
    compact = re.sub(r"[\s\-().]", "", raw)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    if not re.fullmatch(r"\+?\d+", compact):
        return "", f"{raw} is not a phone number: use digits, with the country code chosen or typed as +264"
    if compact.startswith("+"):
        digits = compact[1:]
        code = next((c for c in _KNOWN if digits.startswith(c)), None)
        if code is None:
            code = digits[:3] if len(digits) > 10 else digits[:2]
        national = digits[len(code):]
    elif compact.startswith("0"):
        code, national = DEFAULT_CODE, compact[1:]
    else:
        return "", f"{raw} needs a country code: choose it from the list, or start the number with 0 for South Africa"
    national = national.lstrip("0")
    if not 6 <= len(national) <= 12:
        return "", f"{raw} is too {'short' if len(national) < 6 else 'long'} to be a phone number"
    return f"+{code} {national}", None
