"""E2E tests for agent task dispatch, daemon lifecycle, and issue-agent workflow closure."""

import uuid

import pytest
from rest_framework.test import APIClient

from accounts.models import Daemon, DaemonToken, DaemonWorkspaceBinding, Member, Workspace
from agents.models import Agent, Task
from issues.models import Comment, Issue


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
        user_model = get_user_model()

        self.user = user_model.objects.create_user(email="agenthost@example.com", name="Agent Host")
        self.workspace = Workspace.objects.create(name="Agent WS", slug="agent-ws", issue_prefix="BOT")
        Member.objects.create(workspace=self.workspace, user=self.user, role=Member.ROLE_OWNER)
        self.daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="bot-daemon")
        self.daemon_token, self.daemon_raw_token = DaemonToken.issue(self.daemon)
        DaemonWorkspaceBinding.objects.create(daemon=self.daemon, workspace=self.workspace, created_by=self.user)
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
        daemon_client = APIClient()
        daemon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.daemon_raw_token}")
        claim_resp = daemon_client.post(
            "/api/daemon/tasks/claim",
            {"daemon_id": str(self.daemon.id), "session_id": "session-1", "work_dir": "/tmp/bot"},
            format="json",
        )
        assert claim_resp.status_code == 200, claim_resp.data
        assert claim_resp.data["status"] == "dispatched"
        assert claim_resp.data["agent_name"] == "BotAgent"
        assert claim_resp.data["provider"] == "fake"
        assert "Bot task issue" in claim_resp.data["prompt"]
        assert "Fix the queued task." in claim_resp.data["prompt"]
        assert claim_resp.data["context"]["issue"]["title"] == "Bot task issue"
        assert claim_resp.data["model"] == "fake-model"
        assert claim_resp.data["system_prompt"] == "Use concise status updates."
        assert claim_resp.data["custom_args"] == ["--fake-events", "1"]
        assert claim_resp.data["mcp_config"] == {"servers": {}}
        task.refresh_from_db()
        assert task.status == Task.Status.DISPATCHED

        start_resp = daemon_client.post(f"/api/daemon/tasks/{task.id}/start", {}, format="json")
        assert start_resp.status_code == 200, start_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.RUNNING
        assert task.started_at is not None

        progress_resp = daemon_client.post(
            f"/api/daemon/tasks/{task.id}/progress",
            {"seq": 1, "type": "status", "content": "running", "metadata": {"step": "executing"}},
            format="json",
        )
        assert progress_resp.status_code == 200, progress_resp.data

        messages_resp = daemon_client.post(
            f"/api/daemon/tasks/{task.id}/messages",
            {"messages": [{"seq": 2, "type": "text", "content": "done"}]},
            format="json",
        )
        assert messages_resp.status_code == 200, messages_resp.data

        # Complete
        complete_resp = daemon_client.post(
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

        usage_resp = daemon_client.post(
            f"/api/daemon/tasks/{task.id}/usage",
            {
                "task_id": str(task.id),
                "provider": "fake",
                "model": "fake-model",
                "input_tokens": 10,
                "output_tokens": 2,
            },
            format="json",
        )
        assert usage_resp.status_code == 201, usage_resp.data
        assert usage_resp.data["input_tokens"] == 10

    def test_issue_create_with_agent_assignee_queues_task_and_comment_on_complete(self):
        """Assigning an issue to an agent should enqueue daemon work and publish the result as an agent comment."""
        issue_resp = self.client.post(
            "/api/issues",
            {
                "title": "Investigate failing build",
                "description": "Please run diagnostics and report back.",
                "assignee_type": "agent",
                "assignee_id": str(self.agent.id),
            },
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data

        task = Task.objects.get(issue_id=issue_resp.data["id"], agent=self.agent)
        assert task.status == Task.Status.QUEUED
        assert task.daemon_id == self.daemon.id
        assert task.trigger_summary == ""

        daemon_client = APIClient()
        daemon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.daemon_raw_token}")
        claim_resp = daemon_client.post(
            "/api/daemon/tasks/claim",
            {"daemon_id": str(self.daemon.id)},
            format="json",
        )
        assert claim_resp.status_code == 200, claim_resp.data
        assert claim_resp.data["id"] == str(task.id)
        assert "Investigate failing build" in claim_resp.data["prompt"]
        assert "Please run diagnostics and report back." in claim_resp.data["prompt"]
        assert claim_resp.data["context"]["issue"]["title"] == "Investigate failing build"

        start_resp = daemon_client.post(f"/api/daemon/tasks/{task.id}/start", {}, format="json")
        assert start_resp.status_code == 200, start_resp.data

        complete_resp = daemon_client.post(
            f"/api/daemon/tasks/{task.id}/complete",
            {"result": {"summary": "Build fixed and tests pass."}},
            format="json",
        )
        assert complete_resp.status_code == 200, complete_resp.data

        comment = Comment.objects.get(issue_id=issue_resp.data["id"], author_type="agent")
        assert comment.author_id == self.agent.id
        assert comment.type == Comment.Type.COMMENT
        assert comment.content == "Build fixed and tests pass."

        task.refresh_from_db()
        assert task.status == Task.Status.COMPLETED
        assert task.issue.first_executed_at is not None



    def test_issue_create_terminal_status_with_agent_does_not_queue_task(self):
        issue_resp = self.client.post(
            "/api/issues",
            {
                "title": "Already done",
                "status": "done",
                "assignee_type": "agent",
                "assignee_id": str(self.agent.id),
            },
            format="json",
        )

        assert issue_resp.status_code == 201, issue_resp.data
        assert not Task.objects.filter(issue_id=issue_resp.data["id"], agent=self.agent).exists()

    def test_issue_create_with_agent_without_daemon_is_rejected(self):
        unbound_agent = Agent.objects.create(
            workspace=self.workspace,
            daemon=None,
            name="UnboundBot",
            provider="fake",
            model="fake-model",
            status=Agent.Status.ACTIVE,
        )

        issue_resp = self.client.post(
            "/api/issues",
            {"title": "Cannot dispatch", "assignee_type": "agent", "assignee_id": str(unbound_agent.id)},
            format="json",
        )

        assert issue_resp.status_code == 400, issue_resp.data
        assert "assignee_id" in issue_resp.data
        assert not Issue.objects.filter(title="Cannot dispatch").exists()

    def test_issue_reassignment_to_same_agent_does_not_duplicate_active_task(self):
        issue_resp = self.client.post(
            "/api/issues",
            {"title": "One task only"},
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        issue_id = issue_resp.data["id"]

        for _ in range(2):
            update_resp = self.client.patch(
                f"/api/issues/{issue_id}",
                {"assignee_type": "agent", "assignee_id": str(self.agent.id)},
                format="json",
            )
            assert update_resp.status_code == 200, update_resp.data

        assert Task.objects.filter(issue_id=issue_id, agent=self.agent).count() == 1

    def test_non_assignment_update_after_completion_does_not_requeue_agent_task(self):
        issue_resp = self.client.post(
            "/api/issues",
            {"title": "Do once", "assignee_type": "agent", "assignee_id": str(self.agent.id)},
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        issue_id = issue_resp.data["id"]
        task = Task.objects.get(issue_id=issue_id, agent=self.agent)
        task.status = Task.Status.COMPLETED
        task.save(update_fields=["status", "updated_at"])

        update_resp = self.client.patch(
            f"/api/issues/{issue_id}",
            {"title": "Do once, renamed"},
            format="json",
        )

        assert update_resp.status_code == 200, update_resp.data
        assert Task.objects.filter(issue_id=issue_id, agent=self.agent).count() == 1

    def test_reassigning_issue_to_another_agent_cancels_previous_active_task(self):
        other_agent = Agent.objects.create(
            workspace=self.workspace,
            daemon=self.daemon,
            name="SecondBot",
            provider="fake",
            model="fake-model",
            status=Agent.Status.ACTIVE,
        )
        issue_resp = self.client.post(
            "/api/issues",
            {"title": "Switch agent", "assignee_type": "agent", "assignee_id": str(self.agent.id)},
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        issue_id = issue_resp.data["id"]
        first_task = Task.objects.get(issue_id=issue_id, agent=self.agent)

        update_resp = self.client.patch(
            f"/api/issues/{issue_id}",
            {"assignee_type": "agent", "assignee_id": str(other_agent.id)},
            format="json",
        )

        assert update_resp.status_code == 200, update_resp.data
        first_task.refresh_from_db()
        assert first_task.status == Task.Status.CANCELLED
        second_task = Task.objects.get(issue_id=issue_id, agent=other_agent)
        assert second_task.status == Task.Status.QUEUED
        active_statuses = [Task.Status.QUEUED, Task.Status.DISPATCHED, Task.Status.RUNNING]
        assert Task.objects.filter(issue_id=issue_id, status__in=active_statuses).count() == 1

    def test_batch_reassigning_same_agent_does_not_requeue_completed_task(self):
        issue_resp = self.client.post(
            "/api/issues",
            {"title": "Batch do once", "assignee_type": "agent", "assignee_id": str(self.agent.id)},
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        issue_id = issue_resp.data["id"]
        task = Task.objects.get(issue_id=issue_id, agent=self.agent)
        task.status = Task.Status.COMPLETED
        task.save(update_fields=["status", "updated_at"])

        batch_resp = self.client.post(
            "/api/issues/batch-update",
            {"ids": [issue_id], "assignee_type": "agent", "assignee_id": str(self.agent.id)},
            format="json",
        )

        assert batch_resp.status_code == 200, batch_resp.data
        assert Task.objects.filter(issue_id=issue_id, agent=self.agent).count() == 1

    def test_daemon_lifecycle_requires_token(self):
        task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=self.issue,
            status=Task.Status.QUEUED,
            priority=0,
        )

        anonymous = APIClient()
        claim_resp = anonymous.post(
            "/api/daemon/tasks/claim",
            {"daemon_id": str(self.daemon.id)},
            format="json",
        )
        assert claim_resp.status_code in (401, 403)

        start_resp = anonymous.post(f"/api/daemon/tasks/{task.id}/start", {}, format="json")
        assert start_resp.status_code in (401, 403)

        other_daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="other")
        _token, raw = DaemonToken.issue(other_daemon)
        wrong_client = APIClient()
        wrong_client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
        wrong_resp = wrong_client.post(f"/api/daemon/tasks/{task.id}/start", {}, format="json")
        assert wrong_resp.status_code == 400

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
        daemon_client = APIClient()
        daemon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.daemon_raw_token}")
        daemon_client.post(
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


    def test_member_comment_on_assigned_issue_queues_followup_task_with_context(self):
        issue = Issue.objects.create(
            workspace=self.workspace,
            number=10,
            title="Follow up",
            description="Original work",
            assignee_type="agent",
            assignee_id=self.agent.id,
            creator_type="member",
            creator_id=self.user.id,
        )
        Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=issue,
            status=Task.Status.COMPLETED,
        )

        comment_resp = self.client.post(
            f"/api/issues/{issue.id}/comments",
            {"content": "Please handle the follow-up."},
            format="json",
        )

        assert comment_resp.status_code == 201, comment_resp.data
        task = Task.objects.get(issue=issue, status=Task.Status.QUEUED)
        assert task.agent_id == self.agent.id
        assert str(task.trigger_comment_id) == comment_resp.data["id"]
        assert "comment" in task.trigger_summary.lower()

        daemon_client = APIClient()
        daemon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.daemon_raw_token}")
        claim_resp = daemon_client.post(
            "/api/daemon/tasks/claim",
            {"daemon_id": str(self.daemon.id)},
            format="json",
        )
        assert claim_resp.status_code == 200, claim_resp.data
        assert "Please handle the follow-up." in claim_resp.data["prompt"]
        assert claim_resp.data["context"]["trigger_comment"]["content"] == "Please handle the follow-up."

    def test_workspace_task_complete_endpoint_cannot_publish_agent_comment(self):
        task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=self.issue,
            status=Task.Status.RUNNING,
        )

        complete_resp = self.client.post(
            f"/api/tasks/{task.id}/complete",
            {"result": {"summary": "Agent finished."}},
            format="json",
        )

        assert complete_resp.status_code == 400, complete_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.RUNNING
        assert not Comment.objects.filter(issue=self.issue, content="Agent finished.").exists()

    def test_plain_agent_name_mention_in_comment_queues_mentioned_agent(self):
        other_agent = Agent.objects.create(
            workspace=self.workspace,
            daemon=self.daemon,
            name="SecondBot",
            provider="fake",
            model="fake-model",
            status=Agent.Status.ACTIVE,
        )

        comment_resp = self.client.post(
            f"/api/issues/{self.issue.id}/comments",
            {"content": "Please @SecondBot review this."},
            format="json",
        )

        assert comment_resp.status_code == 201, comment_resp.data
        task = Task.objects.get(issue=self.issue, agent=other_agent)
        assert task.status == Task.Status.QUEUED
        assert str(task.trigger_comment_id) == comment_resp.data["id"]

    def test_mentioning_agent_in_comment_queues_mentioned_agent(self):
        other_agent = Agent.objects.create(
            workspace=self.workspace,
            daemon=self.daemon,
            name="SecondBot",
            provider="fake",
            model="fake-model",
            status=Agent.Status.ACTIVE,
        )

        comment_resp = self.client.post(
            f"/api/issues/{self.issue.id}/comments",
            {"content": f"Please [@SecondBot](mention://agent/{other_agent.id}) review this."},
            format="json",
        )

        assert comment_resp.status_code == 201, comment_resp.data
        task = Task.objects.get(issue=self.issue, agent=other_agent)
        assert task.status == Task.Status.QUEUED
        assert str(task.trigger_comment_id) == comment_resp.data["id"]



    def test_member_comment_during_running_task_queues_separate_followup_task(self):
        issue = Issue.objects.create(
            workspace=self.workspace,
            number=12,
            title="Running followup",
            assignee_type="agent",
            assignee_id=self.agent.id,
            creator_type="member",
            creator_id=self.user.id,
        )
        running_task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=issue,
            status=Task.Status.RUNNING,
        )

        comment_resp = self.client.post(
            f"/api/issues/{issue.id}/comments",
            {"content": "Additional requirement after the daemon claimed the first task."},
            format="json",
        )

        assert comment_resp.status_code == 201, comment_resp.data
        followup = Task.objects.exclude(id=running_task.id).get(issue=issue, agent=self.agent)
        assert followup.status == Task.Status.QUEUED
        assert str(followup.trigger_comment_id) == comment_resp.data["id"]

    def test_assigned_agent_mention_in_same_comment_does_not_duplicate_followup_task(self):
        issue = Issue.objects.create(
            workspace=self.workspace,
            number=13,
            title="No duplicate mention",
            assignee_type="agent",
            assignee_id=self.agent.id,
            creator_type="member",
            creator_id=self.user.id,
        )
        Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=issue,
            status=Task.Status.RUNNING,
        )

        comment_resp = self.client.post(
            f"/api/issues/{issue.id}/comments",
            {"content": "Please @BotAgent handle this follow-up."},
            format="json",
        )

        assert comment_resp.status_code == 201, comment_resp.data
        assert Task.objects.filter(issue=issue, agent=self.agent).count() == 2
        assert (
            Task.objects.filter(issue=issue, agent=self.agent, trigger_comment_id=comment_resp.data["id"]).count()
            == 1
        )

    def test_comment_with_unready_agent_mention_still_saves_comment(self):
        unready_agent = Agent.objects.create(
            workspace=self.workspace,
            daemon=None,
            name="NoDaemonBot",
            provider="fake",
            model="fake-model",
            status=Agent.Status.ACTIVE,
        )

        comment_resp = self.client.post(
            f"/api/issues/{self.issue.id}/comments",
            {"content": f"FYI [@NoDaemonBot](mention://agent/{unready_agent.id})"},
            format="json",
        )

        assert comment_resp.status_code == 201, comment_resp.data
        assert Comment.objects.filter(id=comment_resp.data["id"], issue=self.issue).exists()
        assert not Task.objects.filter(issue=self.issue, agent=unready_agent).exists()

    def test_issue_status_cancelled_cancels_active_task(self):
        issue_resp = self.client.post(
            "/api/issues",
            {"title": "Cancel work", "assignee_type": "agent", "assignee_id": str(self.agent.id)},
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        task = Task.objects.get(issue_id=issue_resp.data["id"], agent=self.agent)

        update_resp = self.client.patch(
            f"/api/issues/{issue_resp.data['id']}",
            {"status": "cancelled"},
            format="json",
        )

        assert update_resp.status_code == 200, update_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.CANCELLED

    def test_backlog_to_todo_queues_assigned_agent_when_no_active_task(self):
        issue = Issue.objects.create(
            workspace=self.workspace,
            number=11,
            title="Start from backlog",
            status=Issue.Status.BACKLOG,
            assignee_type="agent",
            assignee_id=self.agent.id,
            creator_type="member",
            creator_id=self.user.id,
        )

        update_resp = self.client.patch(
            f"/api/issues/{issue.id}",
            {"status": "todo"},
            format="json",
        )

        assert update_resp.status_code == 200, update_resp.data
        task = Task.objects.get(issue=issue, agent=self.agent)
        assert task.status == Task.Status.QUEUED



    def test_reopening_done_issue_with_agent_queues_task(self):
        issue = Issue.objects.create(
            workspace=self.workspace,
            number=14,
            title="Reopen done",
            status=Issue.Status.DONE,
            assignee_type="agent",
            assignee_id=self.agent.id,
            creator_type="member",
            creator_id=self.user.id,
        )

        update_resp = self.client.patch(
            f"/api/issues/{issue.id}",
            {"status": "todo"},
            format="json",
        )

        assert update_resp.status_code == 200, update_resp.data
        task = Task.objects.get(issue=issue, agent=self.agent)
        assert task.status == Task.Status.QUEUED

    def test_issue_status_done_cancels_active_task(self):
        issue_resp = self.client.post(
            "/api/issues",
            {"title": "Done cancels", "assignee_type": "agent", "assignee_id": str(self.agent.id)},
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        task = Task.objects.get(issue_id=issue_resp.data["id"], agent=self.agent)

        update_resp = self.client.patch(
            f"/api/issues/{issue_resp.data['id']}",
            {"status": "done"},
            format="json",
        )

        assert update_resp.status_code == 200, update_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.CANCELLED


    def test_dispatched_task_cannot_complete_or_publish_comment_before_start(self):
        task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=self.issue,
            status=Task.Status.DISPATCHED,
        )
        daemon_client = APIClient()
        daemon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.daemon_raw_token}")

        complete_resp = daemon_client.post(
            f"/api/daemon/tasks/{task.id}/complete",
            {"result": {"summary": "Should wait for start."}},
            format="json",
        )

        assert complete_resp.status_code == 400, complete_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.DISPATCHED
        assert not Comment.objects.filter(issue=self.issue, content="Should wait for start.").exists()


    def test_cancelled_task_cannot_be_failed_by_stale_daemon(self):
        task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=self.issue,
            status=Task.Status.CANCELLED,
        )
        daemon_client = APIClient()
        daemon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.daemon_raw_token}")

        fail_resp = daemon_client.post(
            f"/api/daemon/tasks/{task.id}/fail",
            {"failure_reason": "stale failure"},
            format="json",
        )

        assert fail_resp.status_code == 400, fail_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.CANCELLED

    def test_running_task_can_be_failed_by_daemon(self):
        task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=self.issue,
            status=Task.Status.RUNNING,
        )
        daemon_client = APIClient()
        daemon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.daemon_raw_token}")

        fail_resp = daemon_client.post(
            f"/api/daemon/tasks/{task.id}/fail",
            {"failure_reason": "runtime error"},
            format="json",
        )

        assert fail_resp.status_code == 200, fail_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.FAILED
        assert task.failure_reason == "runtime error"

    def test_cancelled_task_cannot_complete_or_publish_comment(self):
        task = Task.objects.create(
            agent=self.agent,
            daemon=self.daemon,
            issue=self.issue,
            status=Task.Status.CANCELLED,
        )
        daemon_client = APIClient()
        daemon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.daemon_raw_token}")

        complete_resp = daemon_client.post(
            f"/api/daemon/tasks/{task.id}/complete",
            {"result": {"summary": "Should not publish."}},
            format="json",
        )

        assert complete_resp.status_code == 400, complete_resp.data
        task.refresh_from_db()
        assert task.status == Task.Status.CANCELLED
        assert not Comment.objects.filter(issue=self.issue, content="Should not publish.").exists()

    def test_issue_task_endpoints_active_history_messages_cancel_and_rerun(self):
        issue_resp = self.client.post(
            "/api/issues",
            {"title": "Endpoint issue", "assignee_type": "agent", "assignee_id": str(self.agent.id)},
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        issue_id = issue_resp.data["id"]
        task = Task.objects.get(issue_id=issue_id, agent=self.agent)

        active_resp = self.client.get(f"/api/issues/{issue_id}/active-task")
        assert active_resp.status_code == 200, active_resp.data
        assert [item["id"] for item in active_resp.data["tasks"]] == [str(task.id)]

        message_resp = self.client.post(
            f"/api/tasks/{task.id}/messages",
            {"messages": [{"seq": 1, "type": "text", "content": "hello"}]},
            format="json",
        )
        assert message_resp.status_code == 200, message_resp.data
        issue_messages_resp = self.client.get(f"/api/issues/{issue_id}/tasks/{task.id}/messages")
        assert issue_messages_resp.status_code == 200, issue_messages_resp.data
        assert issue_messages_resp.data[0]["content"] == "hello"

        cancel_resp = self.client.post(f"/api/issues/{issue_id}/tasks/{task.id}/cancel", {}, format="json")
        assert cancel_resp.status_code == 200, cancel_resp.data
        assert cancel_resp.data["status"] == Task.Status.CANCELLED

        rerun_resp = self.client.post(f"/api/issues/{issue_id}/rerun", {}, format="json")
        assert rerun_resp.status_code == 201, rerun_resp.data
        assert rerun_resp.data["force_fresh_session"] is True
        assert rerun_resp.data["status"] == Task.Status.QUEUED

        history_resp = self.client.get(f"/api/issues/{issue_id}/task-runs")
        assert history_resp.status_code == 200, history_resp.data
        assert len(history_resp.data) == 2
        assert {item["status"] for item in history_resp.data} == {Task.Status.CANCELLED, Task.Status.QUEUED}

    def test_batch_status_cancelled_cancels_tasks_and_batch_unassign_clears_assignee(self):
        issue_resp = self.client.post(
            "/api/issues",
            {"title": "Batch cancel", "assignee_type": "agent", "assignee_id": str(self.agent.id)},
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        issue_id = issue_resp.data["id"]
        task = Task.objects.get(issue_id=issue_id, agent=self.agent)

        batch_resp = self.client.post(
            "/api/issues/batch-update",
            {"ids": [issue_id], "status": "cancelled", "assignee_type": None, "assignee_id": None},
            format="json",
        )

        assert batch_resp.status_code == 200, batch_resp.data
        task.refresh_from_db()
        issue = Issue.objects.get(id=issue_id)
        assert task.status == Task.Status.CANCELLED
        assert issue.assignee_type is None
        assert issue.assignee_id is None
