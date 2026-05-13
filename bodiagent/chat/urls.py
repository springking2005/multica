"""Chat API routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "chat"

router = DefaultRouter()
router.register("sessions", views.ChatSessionViewSet, basename="session")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "sessions/<uuid:session_id>/messages/",
        views.ChatMessageViewSet.as_view({"get": "list", "post": "create"}),
        name="session-messages",
    ),
]
