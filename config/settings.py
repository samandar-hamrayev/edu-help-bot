"""Django settings for edu-help-bot.

Every environment-specific value is read from environment variables (optionally
loaded from a local ``.env`` file). Defaults are safe for production: DEBUG is
off and a real SECRET_KEY is mandatory unless DEBUG is explicitly enabled.
"""

import json
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in (os.getenv(name) or default).split(",") if item.strip()]


def parse_admin_ids(raw: str) -> frozenset[int]:
    """Parse a comma separated list of Telegram user ids (``TELEGRAM_ADMINS``)."""
    ids = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError as exc:
            raise ImproperlyConfigured(f"TELEGRAM_ADMINS must contain numeric Telegram ids, got {item!r}") from exc
    return frozenset(ids)


def parse_required_chats(raw: str) -> list[tuple[int | str, str]]:
    """Parse ``REQUIRED_CHATS_JSON``: ``[[chat_id, "@username"], ...]``."""
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(f"REQUIRED_CHATS_JSON is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ImproperlyConfigured("REQUIRED_CHATS_JSON must be a JSON list")
    chats: list[tuple[int | str, str]] = []
    for entry in data:
        if not isinstance(entry, list | tuple) or len(entry) < 2:
            raise ImproperlyConfigured('Each REQUIRED_CHATS_JSON entry must be [chat_id, "@username"]')
        chat_id, username = entry[0], str(entry[1]).strip()
        if not username.startswith("@"):
            username = f"@{username}"
        chats.append((chat_id, username))
    return chats


# === Core settings ===
DEBUG = env_bool("DEBUG", default=False)

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Development only: an obviously non-production key.
        SECRET_KEY = "REDACTED"  # noqa: S105
    else:
        raise ImproperlyConfigured("SECRET_KEY environment variable is required when DEBUG is off.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Nginx terminates TLS and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", default=False)
SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", default=not DEBUG)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# === Telegram bot ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Telegram user ids that are always admins. Deliberately NOT named ``ADMINS``:
# that is Django's own setting (list of (name, email) for error mails) and a
# list of ints there crashes the error-reporting log handler on any 500.
# The legacy ``ADMINS`` env var is still accepted as a fallback.
TELEGRAM_ADMINS = parse_admin_ids(os.getenv("TELEGRAM_ADMINS") or os.getenv("ADMINS", ""))
REQUIRED_CHATS = parse_required_chats(os.getenv("REQUIRED_CHATS_JSON", "[]"))
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "")
# How often (seconds) the bot worker polls for answers created in the admin panel.
OUTBOX_POLL_INTERVAL = float(os.getenv("OUTBOX_POLL_INTERVAL", "5"))
# Touched by the outbox loop; the container healthcheck checks its age.
BOT_HEARTBEAT_FILE = os.getenv("BOT_HEARTBEAT_FILE", "/tmp/edu-help-bot.heartbeat")  # noqa: S108

# === Installed apps ===
INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# === Database (PostgreSQL) ===
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "helpbot"),
        "USER": os.getenv("POSTGRES_USER", "helpbot"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": int(os.getenv("POSTGRES_PORT", "5432")),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
    }
}

# === Password validators ===
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# === Internationalization ===
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Tashkent")
USE_I18N = True
USE_TZ = True

# === Static & Media ===
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "mediafiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# === Logging ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "aiogram.event": {"level": "WARNING"},
    },
}

# === Admin UI ===
UNFOLD = {
    "SITE_TITLE": "Edu Help Bot",
    "SITE_HEADER": "Edu Help Bot",
}
