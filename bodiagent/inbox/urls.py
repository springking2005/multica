"""Inbox URL configuration — DRF router with flat action routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ActivityViewSet, InboxViewSet, PinViewSet

app_name = "inbox"


class NoTrailingSlashRouter(DefaultRouter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trailing_slash = ""


router = NoTrailingSlashRouter()
router.register("inbox", InboxViewSet, basename="inbox")
router.register("activities", ActivityViewSet, basename="activity")
router.register("pins", PinViewSet, basename="pin")

# DELETE /api/pins/{item_type}/{item_id} — unpin by type+id pair
unpin_view = PinViewSet.as_view({"delete": "unpin"})

urlpatterns = [
    path("", include(router.urls)),
    path(
        "pins/<str:item_type>/<uuid:item_id>",
        unpin_view,
        name="pin-unpin",
    ),
]
