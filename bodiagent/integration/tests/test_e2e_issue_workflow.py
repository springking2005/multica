"""E2E tests for the issue workflow: create, status transitions, comments, batch update, reorder."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Member, Workspace
from issues.models import Comment, Issue

User = get_user_model()


@pytest.mark.django_db
class TestIssueWorkflow:
    """Critical user journey: create workspace, project, issue, assign to agent,
    transition statuses, comment, batch update, reorder."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.user = User.objects.create_user(email="dev@example.com", name="Dev")
        self.workspace = Workspace.objects.create(name="Dev Workspace", slug="dev-ws", issue_prefix="DEV")
        self.member = Member.objects.create(workspace=self.workspace, user=self.user, role=Member.ROLE_OWNER)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.defaults["HTTP_X_WORKSPACE_ID"] = str(self.workspace.id)

    def test_issue_status_transitions(self):
        """Issue moves through backlog -> todo -> in_progress -> in_review -> done."""
        resp = self.client.post(
            "/api/issues",
            {
                "title": "Status flow test",
                "status": "backlog",
                "creator_type": "member",
                "creator_id": str(self.member.id),
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        issue_id = resp.data["id"]

        transitions = ["todo", "in_progress", "in_review", "done"]
        for status in transitions:
            resp = self.client.put(
                f"/api/issues/{issue_id}",
                {"status": status},
                format="json",
            )
            assert resp.status_code == 200, f"Failed to transition to {status}: {resp.data}"
            assert resp.data["status"] == status

    def test_create_project_and_issue(self):
        """Create project, then create issue assigned to that project."""
        proj_resp = self.client.post(
            "/api/projects",
            {"title": "Sprint 1"},
            format="json",
        )
        assert proj_resp.status_code == 201, proj_resp.data
        project_id = proj_resp.data["id"]

        issue_resp = self.client.post(
            "/api/issues",
            {
                "title": "Implement login",
                "project": project_id,
                "creator_type": "member",
                "creator_id": str(self.member.id),
            },
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        assert str(issue_resp.data["project"]) == project_id

    def test_assign_issue_to_agent(self):
        """Create issue and assign to an agent."""
        from accounts.models import Daemon
        from agents.models import Agent

        daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="test-daemon")
        agent = Agent.objects.create(
            workspace=self.workspace,
            daemon=daemon,
            name="CodeBot",
            provider="claude",
        )

        resp = self.client.post(
            "/api/issues",
            {
                "title": "Bot task",
                "assignee_type": "agent",
                "assignee_id": str(agent.id),
                "creator_type": "member",
                "creator_id": str(self.member.id),
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["assignee_type"] == "agent"
        assert resp.data["assignee_id"] == str(agent.id)

    def test_comment_on_issue(self):
        """Create an issue and add a comment."""
        issue_resp = self.client.post(
            "/api/issues",
            {
                "title": "Comment test",
                "creator_type": "member",
                "creator_id": str(self.member.id),
            },
            format="json",
        )
        assert issue_resp.status_code == 201, issue_resp.data
        issue_id = issue_resp.data["id"]

        comment_resp = self.client.post(
            f"/api/issues/{issue_id}/comments",
            {
                "content": "Hey @testuser, please review this",
                "author_type": "member",
                "author_id": str(self.member.id),
            },
            format="json",
        )
        assert comment_resp.status_code == 201, comment_resp.data
        assert Comment.objects.filter(issue_id=issue_id).exists()

    def test_batch_update_issues(self):
        """Batch update status for multiple issues — create via ORM for unique numbers."""
        issue_ids = []
        for i in range(3):
            issue = Issue.objects.create(
                workspace=self.workspace,
                number=i + 1,
                title=f"Batch issue {i}",
                creator_type="member",
                creator_id=self.member.id,
            )
            issue_ids.append(str(issue.id))

        batch_resp = self.client.post(
            "/api/issues/batch-update",
            {"ids": issue_ids, "status": "in_progress"},
            format="json",
        )
        assert batch_resp.status_code == 200, batch_resp.data
        assert batch_resp.data["updated"] == 3

        for issue_id in issue_ids:
            issue = Issue.objects.get(id=issue_id)
            assert issue.status == "in_progress"

    def test_reorder_issues(self):
        """Reorder issues by position — create via ORM for unique numbers."""
        issue_ids = []
        for i in range(3):
            issue = Issue.objects.create(
                workspace=self.workspace,
                number=i + 1,
                title=f"Reorder issue {i}",
                creator_type="member",
                creator_id=self.member.id,
                position=float(i),
            )
            issue_ids.append(str(issue.id))

        reorder_resp = self.client.post(
            "/api/issues/reorder",
            [
                {"issue_id": issue_ids[2], "position": 0},
                {"issue_id": issue_ids[0], "position": 1},
                {"issue_id": issue_ids[1], "position": 2},
            ],
            format="json",
        )
        assert reorder_resp.status_code == 200, reorder_resp.data
        assert reorder_resp.data["updated"] == 3

    def test_comment_parent_must_belong_to_same_issue_and_workspace(self):
        other_workspace = Workspace.objects.create(name="Other WS", slug="other-issue-parent")
        other_member = Member.objects.create(workspace=other_workspace, user=self.user, role=Member.ROLE_OWNER)
        other_issue = Issue.objects.create(
            workspace=other_workspace,
            number=1,
            title="Other",
            creator_type="member",
            creator_id=other_member.id,
        )
        other_comment = Comment.objects.create(
            workspace=other_workspace,
            issue=other_issue,
            author_type="member",
            author_id=other_member.id,
            content="Other parent",
        )
        issue = Issue.objects.create(
            workspace=self.workspace,
            number=99,
            title="Local",
            creator_type="member",
            creator_id=self.member.id,
        )

        response = self.client.post(
            f"/api/issues/{issue.id}/comments",
            {"content": "Bad reply", "parent": str(other_comment.id)},
            format="json",
        )

        assert response.status_code == 400, response.data

    def test_comment_reaction_uses_url_comment_without_body_comment(self):
        issue = Issue.objects.create(
            workspace=self.workspace,
            number=100,
            title="React",
            creator_type="member",
            creator_id=self.member.id,
        )
        comment = Comment.objects.create(
            workspace=self.workspace,
            issue=issue,
            author_type="member",
            author_id=self.member.id,
            content="React here",
        )

        response = self.client.post(
            f"/api/issues/{issue.id}/comments/{comment.id}/reactions",
            {"actor_type": "member", "actor_id": str(self.member.id), "emoji": "+1"},
            format="json",
        )

        assert response.status_code == 201, response.data
        assert str(response.data["comment"]) == str(comment.id)
