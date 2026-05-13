"""Authenticated accounts API routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "accounts"

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")
router.register("workspaces", views.WorkspaceViewSet, basename="workspace")
router.register("members", views.MemberViewSet, basename="member")
router.register("invitations", views.InvitationViewSet, basename="invitation")
router.register("daemons", views.DaemonViewSet, basename="daemon")
router.register("tokens", views.PATViewSet, basename="token")

urlpatterns = [
    path("", include(router.urls)),
    # Daemon control plane
    path("daemon/register", views.DaemonRegisterView.as_view(), name="daemon-register"),
    path("daemon/heartbeat", views.DaemonHeartbeatView.as_view(), name="daemon-heartbeat"),
    # User profile + onboarding
    path("me", views.me, name="me"),
    path("me/onboarding", views.onboarding, name="onboarding"),
    path("me/onboarding/complete", views.onboarding_complete, name="onboarding-complete"),
    path("me/onboarding/cloud-waitlist", views.cloud_waitlist, name="cloud-waitlist"),
    path("me/starter-content/import", views.starter_content_import, name="starter-content-import"),
    path("me/starter-content/dismiss", views.starter_content_dismiss, name="starter-content-dismiss"),
    path("cli-token", views.cli_token, name="cli-token"),
]
