"""Model and API tests for inbox, activity, and pin."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Workspace
from inbox.models import Activity, InboxItem, Pin

User = get_user_model()
pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user() -> User:
    return User.objects.create_user(email=f"{uuid.uuid4().hex[:8]}@example.com", name="Tester")


@pytest.fixture
def workspace() -> Workspace:
    slug = f"test-{uuid.uuid4().hex[:8]}"
    return Workspace.objects.create(name="Test Workspace", slug=slug)


@pytest.fixture
def api_client(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------------------
# InboxItem model tests
# ---------------------------------------------------------------------------


class TestInboxItemModel:
    def test_create_minimal(self, workspace):
        item = InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=uuid.uuid4(),
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="You were assigned to an issue",
        )
        assert item.id is not None
        assert isinstance(item.id, uuid.UUID)
        assert item.recipient_type == "member"
        assert item.type == InboxItem.Type.ISSUE_ASSIGNED
        assert item.severity == InboxItem.Severity.INFO
        assert item.read is False
        assert item.archived is False
        assert item.details == {}
        assert item.body == ""
        assert item.created_at is not None

    def test_create_full(self, workspace):
        item = InboxItem.objects.create(
            workspace=workspace,
            recipient_type="agent",
            recipient_id=uuid.uuid4(),
            actor_type="member",
            actor_id=uuid.uuid4(),
            type=InboxItem.Type.STATUS_CHANGED,
            severity=InboxItem.Severity.WARNING,
            issue_id=uuid.uuid4(),
            title="Status changed to In Progress",
            body="The issue status was changed.",
            details={"from": "todo", "to": "in_progress"},
            read=True,
            archived=False,
        )
        assert item.actor_type == "member"
        assert item.severity == InboxItem.Severity.WARNING
        assert item.issue_id is not None
        assert item.details == {"from": "todo", "to": "in_progress"}

    def test_str(self, workspace):
        item = InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=uuid.uuid4(),
            type=InboxItem.Type.NEW_COMMENT,
            title="New comment on issue",
        )
        assert str(item).startswith("[new_comment]")

    def test_all_type_choices(self, workspace):
        recipient_id = uuid.uuid4()
        for type_value in InboxItem.Type.values:
            item = InboxItem(
                workspace=workspace,
                recipient_type="member",
                recipient_id=recipient_id,
                type=type_value,
                title=f"Test {type_value}",
            )
            item.full_clean()
            item.save()

    def test_all_severity_choices(self, workspace):
        recipient_id = uuid.uuid4()
        for severity in InboxItem.Severity.values:
            item = InboxItem(
                workspace=workspace,
                recipient_type="member",
                recipient_id=recipient_id,
                type=InboxItem.Type.ISSUE_ASSIGNED,
                severity=severity,
                title="Test",
            )
            item.full_clean()
            item.save()

    def test_ordering(self, workspace):
        recipient_id = uuid.uuid4()
        older = InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=recipient_id,
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="Older",
        )
        newer = InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=recipient_id,
            type=InboxItem.Type.NEW_COMMENT,
            title="Newer",
        )
        items = list(InboxItem.objects.all())
        assert items[0] == newer
        assert items[1] == older


# ---------------------------------------------------------------------------
# Activity model tests
# ---------------------------------------------------------------------------


class TestActivityModel:
    def test_create_activity(self, workspace):
        activity = Activity.objects.create(
            workspace=workspace,
            issue_id=uuid.uuid4(),
            actor_type="member",
            actor_id=uuid.uuid4(),
            action="created",
        )
        assert activity.id is not None
        assert isinstance(activity.id, uuid.UUID)
        assert activity.actor_type == "member"
        assert activity.action == "created"
        assert activity.details == {}
        assert activity.created_at is not None

    def test_create_with_details(self, workspace):
        activity = Activity.objects.create(
            workspace=workspace,
            actor_type="system",
            actor_id=uuid.uuid4(),
            action="status_changed",
            details={"from": "todo", "to": "in_progress"},
        )
        assert activity.details == {"from": "todo", "to": "in_progress"}

    def test_str(self, workspace):
        actor_id = uuid.uuid4()
        activity = Activity.objects.create(
            workspace=workspace,
            actor_type="member",
            actor_id=actor_id,
            action="created",
        )
        assert "created" in str(activity)
        assert str(actor_id) in str(activity)

    def test_ordering(self, workspace):
        actor_id = uuid.uuid4()
        older = Activity.objects.create(
            workspace=workspace,
            actor_type="member",
            actor_id=actor_id,
            action="older",
        )
        newer = Activity.objects.create(
            workspace=workspace,
            actor_type="member",
            actor_id=actor_id,
            action="newer",
        )
        items = list(Activity.objects.all())
        assert items[0] == newer
        assert items[1] == older


# ---------------------------------------------------------------------------
# Pin model tests
# ---------------------------------------------------------------------------


class TestPinModel:
    def test_create_pin(self, user, workspace):
        pin = Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.ISSUE,
            item_id=uuid.uuid4(),
            pinned_by=user,
        )
        assert pin.id is not None
        assert isinstance(pin.id, uuid.UUID)
        assert pin.item_type == Pin.ItemType.ISSUE
        assert pin.position == 0
        assert pin.created_at is not None

    def test_str(self, user, workspace):
        item_id = uuid.uuid4()
        pin = Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.PROJECT,
            item_id=item_id,
            pinned_by=user,
        )
        assert "project" in str(pin)
        assert str(item_id) in str(pin)

    def test_unique_constraint(self, user, workspace):
        item_id = uuid.uuid4()
        Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.ISSUE,
            item_id=item_id,
            pinned_by=user,
        )
        with pytest.raises(Exception):
            Pin.objects.create(
                workspace=workspace,
                item_type=Pin.ItemType.ISSUE,
                item_id=item_id,
                pinned_by=user,
            )

    def test_ordering(self, user, workspace):
        p1 = Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.ISSUE,
            item_id=uuid.uuid4(),
            pinned_by=user,
            position=2,
        )
        p2 = Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.PROJECT,
            item_id=uuid.uuid4(),
            pinned_by=user,
            position=1,
        )
        pins = list(Pin.objects.all())
        assert pins[0] == p2
        assert pins[1] == p1


# ---------------------------------------------------------------------------
# Inbox API tests
# ---------------------------------------------------------------------------


class TestInboxAPI:
    def test_list_inbox(self, api_client, user, workspace):
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="Test",
        )
        response = api_client.get("/api/inbox", HTTP_X_WORKSPACE_ID=str(workspace.id))
        assert response.status_code == 200
        assert response.data["total"] == 1
        assert len(response.data["items"]) == 1

    def test_list_inbox_filter_archived(self, api_client, user, workspace):
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="Active",
            archived=False,
        )
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.NEW_COMMENT,
            title="Archived",
            archived=True,
        )
        response = api_client.get(
            "/api/inbox", HTTP_X_WORKSPACE_ID=str(workspace.id)
        )
        assert response.status_code == 200
        assert response.data["total"] == 1
        assert response.data["items"][0]["title"] == "Active"

    def test_mark_read(self, api_client, user, workspace):
        item = InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="Test",
        )
        response = api_client.post(
            f"/api/inbox/{item.id}/read",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        item.refresh_from_db()
        assert item.read is True

    def test_archive_item(self, api_client, user, workspace):
        item = InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="Test",
        )
        response = api_client.post(
            f"/api/inbox/{item.id}/archive",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        item.refresh_from_db()
        assert item.archived is True

    def test_mark_all_read(self, api_client, user, workspace):
        for i in range(3):
            InboxItem.objects.create(
                workspace=workspace,
                recipient_type="member",
                recipient_id=user.id,
                type=InboxItem.Type.ISSUE_ASSIGNED,
                title=f"Test {i}",
            )
        response = api_client.post(
            "/api/inbox/mark-all-read",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        assert response.data["updated"] == 3

    def test_archive_all(self, api_client, user, workspace):
        for i in range(2):
            InboxItem.objects.create(
                workspace=workspace,
                recipient_type="member",
                recipient_id=user.id,
                type=InboxItem.Type.ISSUE_ASSIGNED,
                title=f"Test {i}",
            )
        response = api_client.post(
            "/api/inbox/archive-all",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        assert response.data["updated"] == 2

    def test_archive_all_read(self, api_client, user, workspace):
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="Read",
            read=True,
        )
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.NEW_COMMENT,
            title="Unread",
            read=False,
        )
        response = api_client.post(
            "/api/inbox/archive-all-read",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        assert response.data["updated"] == 1

    def test_archive_completed(self, api_client, user, workspace):
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.TASK_COMPLETED,
            title="Completed",
        )
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="Other",
        )
        response = api_client.post(
            "/api/inbox/archive-completed",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        assert response.data["updated"] == 1

    def test_unread_count(self, api_client, user, workspace):
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="Unread 1",
        )
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.NEW_COMMENT,
            title="Unread 2",
        )
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=user.id,
            type=InboxItem.Type.STATUS_CHANGED,
            title="Read",
            read=True,
        )
        response = api_client.get(
            "/api/inbox/unread-count",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        assert response.data["count"] == 2

    def test_workspace_header_required(self, api_client):
        response = api_client.get("/api/inbox")
        assert response.status_code == 400
        assert "workspace_id" in response.data


# ---------------------------------------------------------------------------
# Activity API tests
# ---------------------------------------------------------------------------


class TestActivityAPI:
    def test_list_activities(self, api_client, workspace):
        Activity.objects.create(
            workspace=workspace,
            actor_type="member",
            actor_id=uuid.uuid4(),
            action="created",
        )
        response = api_client.get("/api/activities", HTTP_X_WORKSPACE_ID=str(workspace.id))
        assert response.status_code == 200
        assert response.data["total"] == 1
        assert len(response.data["items"]) == 1

    def test_filter_by_issue(self, api_client, workspace):
        issue_a = uuid.uuid4()
        issue_b = uuid.uuid4()
        Activity.objects.create(
            workspace=workspace,
            issue_id=issue_a,
            actor_type="member",
            actor_id=uuid.uuid4(),
            action="created",
        )
        Activity.objects.create(
            workspace=workspace,
            issue_id=issue_b,
            actor_type="member",
            actor_id=uuid.uuid4(),
            action="status_changed",
        )
        response = api_client.get(
            f"/api/activities?issue_id={issue_a}",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        assert response.data["total"] == 1

    def test_workspace_header_required(self, api_client):
        response = api_client.get("/api/activities")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Pin API tests
# ---------------------------------------------------------------------------


class TestPinAPI:
    def test_list_pins(self, api_client, user, workspace):
        Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.ISSUE,
            item_id=uuid.uuid4(),
            pinned_by=user,
        )
        response = api_client.get("/api/pins", HTTP_X_WORKSPACE_ID=str(workspace.id))
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_create_pin(self, api_client, user, workspace):
        item_id = uuid.uuid4()
        response = api_client.post(
            "/api/pins",
            {"item_type": "issue", "item_id": str(item_id)},
            format="json",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 201
        assert response.data["item_type"] == "issue"
        assert response.data["item_id"] == str(item_id)

    def test_create_duplicate_pin_returns_existing(self, api_client, user, workspace):
        item_id = uuid.uuid4()
        pin = Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.ISSUE,
            item_id=item_id,
            pinned_by=user,
        )
        response = api_client.post(
            "/api/pins",
            {"item_type": "issue", "item_id": str(item_id)},
            format="json",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        assert response.data["id"] == str(pin.id)

    def test_unpin(self, api_client, user, workspace):
        item_id = uuid.uuid4()
        Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.ISSUE,
            item_id=item_id,
            pinned_by=user,
        )
        response = api_client.delete(
            f"/api/pins/issue/{item_id}",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        assert Pin.objects.filter(item_id=item_id, pinned_by=user).exists() is False

    def test_reorder_pins(self, api_client, user, workspace):
        item_a = uuid.uuid4()
        item_b = uuid.uuid4()
        Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.ISSUE,
            item_id=item_a,
            pinned_by=user,
            position=0,
        )
        Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.PROJECT,
            item_id=item_b,
            pinned_by=user,
            position=1,
        )
        response = api_client.put(
            "/api/pins/reorder",
            {
                "item_ids": [
                    {"item_type": "project", "item_id": str(item_b)},
                    {"item_type": "issue", "item_id": str(item_a)},
                ]
            },
            format="json",
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert response.status_code == 200
        pin_b = Pin.objects.get(item_id=item_b, pinned_by=user)
        pin_a = Pin.objects.get(item_id=item_a, pinned_by=user)
        assert pin_b.position == 0
        assert pin_a.position == 1

    def test_scoped_to_user(self, api_client, user, workspace):
        other_user = User.objects.create_user(
            email=f"{uuid.uuid4().hex[:8]}@example.com", name="Other"
        )
        Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.ISSUE,
            item_id=uuid.uuid4(),
            pinned_by=user,
        )
        Pin.objects.create(
            workspace=workspace,
            item_type=Pin.ItemType.PROJECT,
            item_id=uuid.uuid4(),
            pinned_by=other_user,
        )
        response = api_client.get("/api/pins", HTTP_X_WORKSPACE_ID=str(workspace.id))
        assert response.status_code == 200
        assert len(response.data) == 1


# ---------------------------------------------------------------------------
# Listener helpers tests
# ---------------------------------------------------------------------------


class TestListenerHelpers:
    def test_create_activity(self, workspace):
        from inbox.listeners import create_activity

        activity = create_activity(
            workspace_id=str(workspace.id),
            issue_id=str(uuid.uuid4()),
            actor_type="member",
            actor_id=str(uuid.uuid4()),
            action="created",
            details={"key": "value"},
        )
        assert activity.action == "created"
        assert activity.details == {"key": "value"}

    def test_create_inbox_respects_actor_skip(self, workspace):
        from inbox.listeners import _create_inbox

        actor_id = str(uuid.uuid4())
        result = _create_inbox(
            workspace_id=str(workspace.id),
            recipient_type="member",
            recipient_id=actor_id,
            actor_type="member",
            actor_id=actor_id,
            inbox_type="issue_assigned",
            severity="info",
            issue_id=None,
            title="Test",
            body="",
        )
        assert result is None  # skipped because recipient == actor

    def test_archive_task_failed(self, workspace):
        from inbox.listeners import archive_task_failed_for_issue

        issue_id = str(uuid.uuid4())
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=uuid.uuid4(),
            type=InboxItem.Type.TASK_FAILED,
            title="Failed",
            issue_id=issue_id,
        )
        InboxItem.objects.create(
            workspace=workspace,
            recipient_type="member",
            recipient_id=uuid.uuid4(),
            type=InboxItem.Type.ISSUE_ASSIGNED,
            title="Other",
            issue_id=issue_id,
        )
        count = archive_task_failed_for_issue(str(workspace.id), issue_id)
        assert count == 1
        assert InboxItem.objects.filter(issue_id=issue_id, type=InboxItem.Type.TASK_FAILED, archived=True).exists()
