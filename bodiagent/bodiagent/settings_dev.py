"""Development settings — auto-loaded by manage.py and pytest."""

from .settings import *

DEBUG = True
ALLOWED_HOSTS = ["*"]
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

# Dev DB — use SQLite for fast iteration when PostgreSQL unavailable
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Dev Redis — optional, skip if not available
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = True

# Dev email — print to console
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Dev auth — bypass email verification
BODIAGENT_DEV_VERIFICATION_CODE = "888888"
BODIAGENT_SKIP_EMAIL = True
