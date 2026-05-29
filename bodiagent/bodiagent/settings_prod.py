import logging
import os
import sys

import structlog

from .settings import *


def _csv_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def _bool_env(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required for bodiagent.settings_prod")
    return value


DEBUG = False
ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS")
SECRET_KEY = _required_env("DJANGO_SECRET_KEY")

if not ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS must contain at least one host for bodiagent.settings_prod")

CORS_ALLOWED_ORIGINS = _csv_env("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = _csv_env("CSRF_TRUSTED_ORIGINS")

STATIC_ROOT = os.environ.get("STATIC_ROOT", BASE_DIR / "staticfiles")
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", BASE_DIR / "data" / "uploads")

# Production DB
# This app is served through ASGI (gunicorn + uvicorn). Django recommends
# disabling persistent database connections in async mode; otherwise each
# worker/thread can hold idle PostgreSQL sessions for DB_CONN_MAX_AGE seconds
# and small self-hosted databases can hit max_connections during traffic,
# deploys, or smoke tests. Operators that put PgBouncer / a psycopg pool in
# front may still opt in explicitly with DB_CONN_MAX_AGE.
DATABASES["default"].update({
    "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "0")),
    "OPTIONS": {"sslmode": os.environ.get("DB_SSLMODE", "prefer")},
})

# Production Redis
REDIS_URL = _required_env("REDIS_URL")
CHANNEL_LAYERS["default"]["CONFIG"]["hosts"] = [REDIS_URL]
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# Production email — use SMTP
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("SMTP_HOST", "")
EMAIL_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_USE_TLS = _bool_env("SMTP_USE_TLS", True)
EMAIL_USE_SSL = _bool_env("SMTP_USE_SSL", False)
EMAIL_HOST_USER = os.environ.get("SMTP_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_TIMEOUT = int(os.environ.get("SMTP_TIMEOUT", "10"))

# Sentry
if sentry_dsn := os.environ.get("SENTRY_DSN"):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[DjangoIntegration()],
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        send_default_pii=False,
    )

# Structured logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FORMAT = os.environ.get("LOG_FORMAT", "json")
LOG_LEVEL_NO = logging.getLevelName(LOG_LEVEL.upper())
if not isinstance(LOG_LEVEL_NO, int):
    LOG_LEVEL_NO = logging.INFO
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer()
        if LOG_FORMAT == "json"
        else structlog.dev.ConsoleRenderer(colors=False),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL_NO),
    cache_logger_on_first_use=True,
)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "structlog.stdlib.ProcessorFormatter",
            "processor": structlog.processors.JSONRenderer(),
        },
        "plain": {
            "format": "%(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "plain" if LOG_FORMAT != "json" else "json",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.server": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "bodiagent": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

# Security
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _bool_env("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", SECURE_SSL_REDIRECT)
CSRF_COOKIE_SECURE = _bool_env("CSRF_COOKIE_SECURE", SECURE_SSL_REDIRECT)
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000" if SECURE_SSL_REDIRECT else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _bool_env("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = _bool_env("SECURE_HSTS_PRELOAD", False)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"

# The production image is commonly run directly by ASGI on port 8000 during
# smoke testing and small deployments.  Serve collected/staticfinder assets in
# that topology so login pages do not emit missing CSS/MIME errors when no
# reverse proxy is configured for /static/.
BODIAGENT_SERVE_STATIC = _bool_env("BODIAGENT_SERVE_STATIC", True)
