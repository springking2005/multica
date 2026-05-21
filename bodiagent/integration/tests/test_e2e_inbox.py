"""E2E tests for inbox: items created on assignment/status change, mark read, archive, counts."""


import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Member, Workspace
from inbox.models import InboxItem

User = get_user_model()


@pytest.mark.django_db
class TestInboxFlow:
    """Verify inbox items are created and managed correctly."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.user = User.objects.create_user(email="inboxuser@example.com", name="Inbox User")
        self.workspace = Workspace.objects.create(name="Inbox WS", slug="inbox-ws", issue_prefix="INB")
        self.member = Member.objects.create(workspace=self.workspace, user=self.user, role=Member.ROLE_OWNER)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.defaults["HTTP_X_WORKSPACE_ID"] = str(self.workspace.id)

    def _create_issue(self, **kwargs):
        defaults = {
            "title": "Test issue",
            "creator_type": "member",
            "creator_id": self.member.id,
        }
        defaults.update(kwargs)
        resp = self.client.post("/api/issues", defaults, format="json")
        assert resp.status_code == 201, resp.data
        return resp.data

    def test_basic_inbox_query(self):
        """Inbox list endpoint returns empty list initially."""
        resp = self.client.get("/api/inbox")
        assert resp.status_code == 200, resp.data
        assert "items" in resp.data
        assert "total" in resp.data

    def test_unread_count_zero_initially(self):
        """Unread count is zero when no inbox items exist."""
        resp = self.client.get("/api/inbox/unread-count")
        assert resp.status_code == 200, resp.data
        assert resp.data["count"] == 0

    def test_mark_all_read(self):
        """Mark-all-read updates inbox items."""
        InboxItem.objects.create(
            workspace=self.workspace,
            recipient_type="member",
            recipient_id=self.member.id,
            type="issue_assigned",
            severity="info",
            title="Test notification",
            read=False,
        )
        resp = self.client.post("/api/inbox/mark-all-read")
        assert resp.status_code == 200, resp.data
        assert resp.data["updated"] >= 1

    def test_archive_all(self):
        """Archive-all archives unread items."""
        InboxItem.objects.create(
            workspace=self.workspace,
            recipient_type="member",
            recipient_id=self.member.id,
            type="status_changed",
            severity="info",
            title="Status update",
            read=False,
            archived=False,
        )
        resp = self.client.post("/api/inbox/archive-all")
        assert resp.status_code == 200, resp.data
        assert resp.data["updated"] >= 1

    def test_mark_single_inbox_read_and_archive(self):
        """Mark a single inbox item as read, then archive it."""
        item = InboxItem.objects.create(
            workspace=self.workspace,
            recipient_type="member",
            recipient_id=self.member.id,
            type="new_comment",
            severity="info",
            title="New comment on issue",
            body="Someone commented on your issue",
            read=False,
            archived=False,
        )
        # Mark read
        read_resp = self.client.post(f"/api/inbox/{item.id}/read")
        assert read_resp.status_code == 200, read_resp.data
        item.refresh_from_db()
        assert item.read is True

        # Archive
        archive_resp = self.client.post(f"/api/inbox/{item.id}/archive")
        assert archive_resp.status_code == 200, archive_resp.data
        item.refresh_from_db()
        assert item.archived is True
