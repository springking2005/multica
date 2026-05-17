"""Agent, task, skill, and daemon control plane URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AgentViewSet,
    DaemonControlView,
    DaemonTaskLifecycleView,
    SkillViewSet,
    TaskUsageDailyViewSet,
    TaskUsageViewSet,
    TaskViewSet,
)

app_name = "agents"


class NoTrailingSlashRouter(DefaultRouter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trailing_slash = ""


router = NoTrailingSlashRouter()
router.register("agents", AgentViewSet, basename="agent")
router.register("skills", SkillViewSet, basename="skill")
router.register("tasks", TaskViewSet, basename="task")
router.register("task-usage", TaskUsageViewSet, basename="task-usage")
router.register("task-usage-daily", TaskUsageDailyViewSet, basename="task-usage-daily")

urlpatterns = [
    path("", include(router.urls)),
    # Daemon control plane
    path(
        "daemon/tasks/claim",
        DaemonControlView.as_view(),
        name="daemon-task-claim",
    ),
    # Task lifecycle (nested under daemon for daemon-side operations)
    path(
        "daemon/tasks/<uuid:task_id>/start",
        DaemonTaskLifecycleView.as_view({"post": "post_start"}),
        name="daemon-task-start",
    ),
    path(
        "daemon/tasks/<uuid:task_id>/progress",
        DaemonTaskLifecycleView.as_view({"post": "post_progress"}),
        name="daemon-task-progress",
    ),
    path(
        "daemon/tasks/<uuid:task_id>/complete",
        DaemonTaskLifecycleView.as_view({"post": "post_complete"}),
        name="daemon-task-complete",
    ),
    path(
        "daemon/tasks/<uuid:task_id>/fail",
        DaemonTaskLifecycleView.as_view({"post": "post_fail"}),
        name="daemon-task-fail",
    ),
    path(
        "daemon/tasks/<uuid:task_id>/usage",
        DaemonTaskLifecycleView.as_view({"post": "post_usage"}),
        name="daemon-task-usage",
    ),
    path(
        "daemon/tasks/<uuid:task_id>/messages",
        DaemonTaskLifecycleView.as_view({"get": "get_messages", "post": "post_messages"}),
        name="daemon-task-messages",
    ),
    path(
        "daemon/tasks/<uuid:task_id>/status",
        DaemonTaskLifecycleView.as_view({"get": "get_status"}),
        name="daemon-task-status",
    ),
]
