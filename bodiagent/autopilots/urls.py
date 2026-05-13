"""Autopilot URL configuration — DRF router with nested routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AutopilotRunViewSet, AutopilotTriggerViewSet, AutopilotViewSet


class NoTrailingSlashRouter(DefaultRouter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trailing_slash = ""


router = NoTrailingSlashRouter()
router.register("autopilots", AutopilotViewSet, basename="autopilot")

trigger_create = AutopilotTriggerViewSet.as_view({"post": "create"})
trigger_update = AutopilotTriggerViewSet.as_view({"patch": "update"})
trigger_delete = AutopilotTriggerViewSet.as_view({"delete": "destroy"})

run_list = AutopilotRunViewSet.as_view({"get": "list"})
run_detail = AutopilotRunViewSet.as_view({"get": "retrieve"})

urlpatterns = [
    path("", include(router.urls)),
    # Trigger routes nested under autopilots
    path(
        "autopilots/<uuid:autopilot_id>/triggers",
        trigger_create,
        name="autopilot-trigger-create",
    ),
    path(
        "autopilots/<uuid:autopilot_id>/triggers/<uuid:trigger_id>",
        trigger_update,
        name="autopilot-trigger-update",
    ),
    path(
        "autopilots/<uuid:autopilot_id>/triggers/<uuid:trigger_id>/delete",
        trigger_delete,
        name="autopilot-trigger-delete",
    ),
    # Run routes nested under autopilots
    path(
        "autopilots/<uuid:autopilot_id>/runs",
        run_list,
        name="autopilot-run-list",
    ),
    path(
        "autopilots/<uuid:autopilot_id>/runs/<uuid:run_id>",
        run_detail,
        name="autopilot-run-detail",
    ),
]
