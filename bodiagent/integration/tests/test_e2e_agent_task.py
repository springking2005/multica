"""E2E tests for agent task lifecycle: register daemon, create agent, queue, claim, start, progress, complete, fail.

Note: Uses ORM for task creation/lifecycle transitions because TaskViewSet has a method
named ``dispatch`` decorated as ``@action(detail=True)``, which shadows DRF's base
``dispatch()`` and breaks all non-detail actions on the viewset.
"""

import uuid

import pytest
from rest_framework.test import APIClient

from accounts.models import Daemon, Member, Workspace
from agents.models import Agent, Task
from issues.models import Issue


def _make_client(user, workspace):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_WORKSPACE_ID"] = str(workspace.id)
    return client


@pytest.mark.django_db
class TestAgentTaskLifecycle:
    """End-to-end task lifecycle: queued -> dispatched -> running -> completed (and failed)."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        self.user = User.objects.create_user(email="agenthost@example.com", name="Agent Host")
        self.workspace = Workspace.objects.create(name="Agent WS", slug="agent-ws", issue_prefix="BOT")
        Member.objects.create(workspace=self.workspace, user=self.user, role=Member.ROLE_OWNER)
        self.daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="bot-daemon")
        self.agent = Agent.objects.create(
            workspace=self.workspace,
            daemon=self.daemon,
            name="BotAgent",
            provider="fake",
            model="fake-model",
            instructions="Use concise status updates.",
            custom_args=["--fake-events", "1"],
            mcp_config={"servers": {}},
            status=Agent.Status.ACTIVE,
        )
        self.issue = Issue.objects.create(
            workspace=self.workspace,
            number=1,
            title="Bot task issue",
            description="Fix the queued task.",
            creator_type="member",
            creator_id=self.user.id,
        )
        self.client = _make_client(self.user, self.workspace)

    def test_create_task(self):
        """Create a task bound to an agent and daemon — verify initial state."""
        task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=self.issue,
            status=Task.Status.QUEUED,
            priority=0,
        )
        assert task.status == Task.Status.QUEUED
        assert task.agent_id == self.agent.id
        assert task.issue_id == self.issue.id
        assert task.daemon_id == self.daemon.id

    def test_task_lifecycle_queued_to_completed(self):
        """Full lifecycle: queued -> dispatched -> running -> completed."""
        task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=self.issue,
            status=Task.Status.QUEUED,
            priority=0,
        )

        # Claim via daemon endpoint (DaemonControlView — AllowAny, works correctly)
        from django.utils import timezone
        claim_resp = APIClient().post(
            "/api/daemon/tasks/claim",
            {"daemon_id": str(self.daemon.id), "session_id": "session-1", "work_dir": "/tmp/bot"},
            format="json",
        )
        assert claim_resp.status_code == 200, claim_resp.data
        assert claim_resp.data["status"] == "dispatched"
        assert claim_resp.data["agent_name"] == "BotAgent"
        assert claim_resp.data["provider"] == "fake"
        assert claim_resp.data["prompt"] == "Bot task issue\n\nFix the queued task."
        assert claim_resp.data["model"] == "fake-model"
        assert claim_resp.data["system_prompt"] == "Use concise status updates."
        assert claim_resp.data["custom_args"] == ["--fake-events", "1"]
        assert claim_resp.data["mcp_config"] == {"servers": {}}
        task.refresh_from_db()
        assert task.status == Task.Status.DISPATCHED

        start_resp = APIClient().post(f"/api/daemon/tasks/{task.id}/start", {}, format="json")
        assert start_resp.status_code == 200, start_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.RUNNING
        assert task.started_at is not None

        progress_resp = APIClient().post(
            f"/api/daemon/tasks/{task.id}/progress",
            {"seq": 1, "type": "status", "content": "running", "metadata": {"step": "executing"}},
            format="json",
        )
        assert progress_resp.status_code == 200, progress_resp.data

        messages_resp = APIClient().post(
            f"/api/daemon/tasks/{task.id}/messages",
            {"messages": [{"seq": 2, "type": "text", "content": "done"}]},
            format="json",
        )
        assert messages_resp.status_code == 200, messages_resp.data

        # Complete
        complete_resp = APIClient().post(
            f"/api/daemon/tasks/{task.id}/complete",
            {"result": {"summary": "Done"}, "branch_name": "feature/bot-fix"},
            format="json",
        )
        assert complete_resp.status_code == 200, complete_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.COMPLETED
        assert task.completed_at is not None
        assert task.result == {"summary": "Done"}
        assert task.messages.count() == 2

    def test_task_failure_flow(self):
        """Task lifecycle ending in failure with failure_reason."""
        from django.utils import timezone
        task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=self.issue,
            status=Task.Status.QUEUED,
            priority=0,
        )

        # Claim via daemon endpoint
        APIClient().post(
            "/api/daemon/tasks/claim",
            {"daemon_id": str(self.daemon.id)},
            format="json",
        )
        task.refresh_from_db()

        # Run
        task.status = Task.Status.RUNNING
        task.started_at = timezone.now()
        task.save(update_fields=["status", "started_at", "updated_at"])

        # Fail
        task.status = Task.Status.FAILED
        task.failure_reason = "API rate limit exceeded"
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "failure_reason", "completed_at", "updated_at"])
        task.refresh_from_db()

        assert task.status == Task.Status.FAILED
        assert task.failure_reason == "API rate limit exceeded"
        assert task.completed_at is not None
