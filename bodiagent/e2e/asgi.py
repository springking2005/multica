"""ASGI entrypoint for Playwright tests that need real WebSockets.

This module is imported by a standalone Daphne subprocess.  It mirrors
``bodiagent.asgi`` while applying pytest's runtime-only database and session
settings before Django builds the ASGI application.
"""

from __future__ import annotations

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bodiagent.settings_dev")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

from django.conf import settings  # noqa: E402
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

sqlite_name = os.environ.get("BODIAGENT_TEST_SQLITE_NAME")
if sqlite_name and settings.DATABASES["default"].get("ENGINE") == "django.db.backends.sqlite3":
    settings.DATABASES["default"]["NAME"] = sqlite_name
    settings.DATABASES["default"].setdefault("TEST", {})["NAME"] = sqlite_name

settings.SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.layers import channel_layers  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from django.urls import path  # noqa: E402

channel_layers.backends = {}
django_asgi_app = ASGIStaticFilesHandler(get_asgi_application())

from chat.consumers import ChatConsumer  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(
                    [
                        path("ws/chat/<str:session_id>/", ChatConsumer.as_asgi()),
                    ]
                )
            )
        ),
    }
)
