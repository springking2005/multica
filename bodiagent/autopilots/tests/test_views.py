"""View tests for autopilots app."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from autopilots.models import Autopilot, AutopilotTrigger

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def user() -> User:
    return User.objects.create_user(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        name="Test User",
        password="testpass123",
    )


@pytest.fixture
def api_client(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _ws_headers(workspace) -> dict:
    return {"HTTP_X_WORKSPACE_ID": str(workspace.id)}


class TestAutopilotViewSet:
    def test_list_empty(self, api_client, workspace):
        url = reverse("autopilot-list")
        response = api_client.get(url, **_ws_headers(workspace))
        assert response.status_code == 200
        assert response.data["results"] == []

    def test_list_autopilots(self, api_client, workspace, autopilot):
        url = reverse("autopilot-list")
        response = api_client.get(url, **_ws_headers(workspace))
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["title"] == "Test Autopilot"

    def test_create_autopilot(self, api_client, workspace, agent, user):
        url = reverse("autopilot-list")
        data = {
            "title": "New Autopilot",
            "assignee": str(agent.id),
            "created_by_type": "member",
            "created_by_id": str(workspace.members.get(user=user).id),
        }
        response = api_client.post(
            url, data, format="json", **_ws_headers(workspace)
        )
        assert response.status_code == 201
        assert response.data["title"] == "New Autopilot"
        assert response.data["status"] == "active"

    def test_retrieve_autopilot(self, api_client, workspace, autopilot):
        url = reverse(
            "autopilot-detail", kwargs={"autopilot_id": str(autopilot.id)}
        )
        response = api_client.get(url, **_ws_headers(workspace))
        assert response.status_code == 200
        assert response.data["title"] == "Test Autopilot"

    def test_update_autopilot(self, api_client, workspace, autopilot):
        url = reverse(
            "autopilot-detail", kwargs={"autopilot_id": str(autopilot.id)}
        )
        response = api_client.patch(
            url, {"title": "Updated"}, format="json", **_ws_headers(workspace)
        )
        assert response.status_code == 200
        assert response.data["title"] == "Updated"

    def test_delete_autopilot(self, api_client, workspace, autopilot):
        url = reverse(
            "autopilot-detail", kwargs={"autopilot_id": str(autopilot.id)}
        )
        response = api_client.delete(url, **_ws_headers(workspace))
        assert response.status_code == 200
        assert response.data == {"ok": True}
        assert not Autopilot.objects.filter(id=autopilot.id).exists()

    def test_enable_autopilot(self, api_client, workspace, autopilot):
        autopilot.status = Autopilot.Status.PAUSED
        autopilot.save()
        url = reverse(
            "autopilot-enable", kwargs={"autopilot_id": str(autopilot.id)}
        )
        response = api_client.post(url, **_ws_headers(workspace))
        assert response.status_code == 200
        autopilot.refresh_from_db()
        assert autopilot.status == Autopilot.Status.ACTIVE

    def test_disable_autopilot(self, api_client, workspace, autopilot):
        url = reverse(
            "autopilot-disable", kwargs={"autopilot_id": str(autopilot.id)}
        )
        response = api_client.post(url, **_ws_headers(workspace))
        assert response.status_code == 200
        autopilot.refresh_from_db()
        assert autopilot.status == Autopilot.Status.PAUSED

    def test_manual_trigger(self, api_client, workspace, autopilot):
        url = reverse(
            "autopilot-trigger-manual",
            kwargs={"autopilot_id": str(autopilot.id)},
        )
        response = api_client.post(url, format="json", **_ws_headers(workspace))
        assert response.status_code == 201
        assert response.data["source"] == "manual"

    def test_list_runs(self, api_client, workspace, autopilot_run):
        autopilot = autopilot_run.autopilot
        url = reverse(
            "autopilot-list-runs",
            kwargs={"autopilot_id": str(autopilot.id)},
        )
        response = api_client.get(url, **_ws_headers(workspace))
        assert response.status_code == 200
        assert len(response.data["results"]) >= 1

    def test_missing_workspace_id(self, api_client):
        url = reverse("autopilot-list")
        response = api_client.get(url)
        assert response.status_code == 400


class TestAutopilotTriggerViewSet:
    def test_create_trigger(self, api_client, workspace, autopilot):
        url = reverse(
            "autopilot-trigger-create",
            kwargs={"autopilot_id": str(autopilot.id)},
        )
        data = {
            "kind": "schedule",
            "cron_expression": "0 */6 * * *",
            "label": "Every 6 hours",
        }
        response = api_client.post(
            url, data, format="json", **_ws_headers(workspace)
        )
        assert response.status_code == 201
        assert response.data["kind"] == "schedule"
        assert response.data["label"] == "Every 6 hours"

    def test_update_trigger(self, api_client, workspace, schedule_trigger):
        autopilot = schedule_trigger.autopilot
        url = reverse(
            "autopilot-trigger-update",
            kwargs={
                "autopilot_id": str(autopilot.id),
                "trigger_id": str(schedule_trigger.id),
            },
        )
        response = api_client.patch(
            url, {"enabled": False}, format="json", **_ws_headers(workspace)
        )
        assert response.status_code == 200
        schedule_trigger.refresh_from_db()
        assert schedule_trigger.enabled is False

    def test_delete_trigger(self, api_client, workspace, schedule_trigger):
        autopilot = schedule_trigger.autopilot
        trigger_id = schedule_trigger.id
        url = reverse(
            "autopilot-trigger-delete",
            kwargs={
                "autopilot_id": str(autopilot.id),
                "trigger_id": str(trigger_id),
            },
        )
        response = api_client.delete(url, **_ws_headers(workspace))
        assert response.status_code == 200
        assert not AutopilotTrigger.objects.filter(id=trigger_id).exists()

    def test_trigger_wrong_autopilot(self, api_client, workspace, agent, schedule_trigger):
        """Trigger belongs to a different autopilot (enforced by URL pattern match)."""
        other_ap = Autopilot.objects.create(
            workspace=workspace,
            title="Other AP",
            assignee=agent,
            created_by_type="member",
            created_by_id=workspace.members.first().id,
        )
        url = reverse(
            "autopilot-trigger-update",
            kwargs={
                "autopilot_id": str(other_ap.id),
                "trigger_id": str(schedule_trigger.id),
            },
        )
        response = api_client.patch(
            url, {"enabled": False}, format="json", **_ws_headers(workspace)
        )
        assert response.status_code == 404


class TestAutopilotRunViewSet:
    def test_list_runs(self, api_client, workspace, autopilot_run):
        autopilot = autopilot_run.autopilot
        url = reverse(
            "autopilot-run-list",
            kwargs={"autopilot_id": str(autopilot.id)},
        )
        response = api_client.get(url, **_ws_headers(workspace))
        assert response.status_code == 200
        assert len(response.data["results"]) >= 1

    def test_retrieve_run(self, api_client, workspace, autopilot_run):
        autopilot = autopilot_run.autopilot
        url = reverse(
            "autopilot-run-detail",
            kwargs={
                "autopilot_id": str(autopilot.id),
                "run_id": str(autopilot_run.id),
            },
        )
        response = api_client.get(url, **_ws_headers(workspace))
        assert response.status_code == 200
        assert response.data["status"] == "completed"
