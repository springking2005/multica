"""ASGI config — HTTP + WebSocket via Django Channels."""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bodiagent.settings_dev")

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from django.urls import path  # noqa: E402

from chat.consumers import ChatConsumer  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter([
                path("ws/chat/<str:session_id>/", ChatConsumer.as_asgi()),
            ])
        )
    ),
})
