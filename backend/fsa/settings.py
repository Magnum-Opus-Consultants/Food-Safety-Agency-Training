"""Django settings for the FSA Academy Training Hub API."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes")


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-for-production")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Demo mode: seeded accounts sign in from a picker, and the business clock is pinned
# (default 2026-09-09, the prototype's date) and can be moved by the training manager.
DEMO_MODE = env_bool("FSA_DEMO_MODE", True)
# Blank = the real date. Set (YYYY-MM-DD) to pin the business date, e.g. for a scripted walkthrough.
DEMO_TODAY = os.environ.get("FSA_DEMO_TODAY", "")

# POPIA: keys for identity numbers (see core/pii.py). Production must supply both; development
# derives stable keys from the secret key so a fresh checkout works.
def _dev_key(purpose):
    import base64
    import hashlib

    return base64.urlsafe_b64encode(hashlib.sha256(f"{purpose}:{SECRET_KEY}".encode()).digest()).decode()


FSA_PII_ENCRYPTION_KEY = os.environ.get("FSA_PII_ENCRYPTION_KEY") or (_dev_key("pii-encryption") if DEBUG else None)
FSA_PII_INDEX_KEY = os.environ.get("FSA_PII_INDEX_KEY") or (_dev_key("pii-index") if DEBUG else None)
if not (FSA_PII_ENCRYPTION_KEY and FSA_PII_INDEX_KEY):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Set FSA_PII_ENCRYPTION_KEY and FSA_PII_INDEX_KEY (32-byte url-safe base64) outside development.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "core",
    "identity",
    "audit",
    "courses",
    "demand",
    "delivery",
    "learners",
    "assurance",
    "oversight",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "fsa.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "fsa.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PGDATABASE", "fsa_training"),
        "USER": os.environ.get("PGUSER", "fsa"),
        "PASSWORD": os.environ.get("PGPASSWORD", "fsa"),
        "HOST": os.environ.get("PGHOST", "localhost"),
        "PORT": os.environ.get("PGPORT", "5433"),
        "ATOMIC_REQUESTS": False,
        "TEST": {"CHARSET": "UTF8", "TEMPLATE": "template0"},
    }
}

AUTH_USER_MODEL = "identity.Account"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-za"
TIME_ZONE = "Africa/Johannesburg"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Sessions and CSRF: the browser reaches Django through the Next.js /api proxy on the same
# origin, so cookies are first-party and no CORS is needed.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:3210,http://127.0.0.1:3210"
).split(",")
SESSION_COOKIE_AGE = 60 * 60 * 10

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Tests hash the seeded passwords with a fast hasher; everything else uses Django's PBKDF2 default.
import sys  # noqa: E402

# Uploaded evidence (Grade 10 documents). Private: never served as static files, only streamed by the
# API to a signed-in user with the learners segment. Object storage replaces this folder in production.
FSA_FILE_ROOT = Path(os.environ.get("FSA_FILE_ROOT", BASE_DIR / "private-files"))
FSA_UPLOAD_MAX_BYTES = 5 * 1024 * 1024

if len(sys.argv) > 1 and sys.argv[1] == "test":
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    # The acceptance tests check the prototype's scenarios, which are dated around 2026-09-09.
    DEMO_TODAY = "2026-09-09"
    import tempfile
    FSA_FILE_ROOT = Path(tempfile.mkdtemp(prefix="fsa-test-files-"))
