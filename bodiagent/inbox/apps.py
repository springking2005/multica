"""Inbox app configuration — registers signal listeners on ready."""

from django.apps import AppConfig


class InboxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inbox"
    label = "inbox"

    def ready(self) -> None:
        # Import listeners to register signal handlers.
        try:
            import inbox.listeners  # noqa: F401
        except ModuleNotFoundError:
            pass
