import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import Daemon, DaemonToken, DaemonWorkspaceBinding, Member, Workspace
from agents.models import Agent
from autopilots.models import Autopilot
from chat.models import ChatSession
from inbox.models import InboxItem
from issues.models import Issue
from projects.models import Project


@pytest.mark.django_db
def test_workspace_scope_rejects_non_member_for_projects(django_user_model):
    user = django_user_model.objects.create_user(email="member@example.com", name="Member")
    other = django_user_model.objects.create_user(email="other@example.com", name="Other")
    allowed = Workspace.objects.create(name="Allowed", slug="allowed")
    forbidden = Workspace.objects.create(name="Forbidden", slug="forbidden")
    Member.objects.create(workspace=allowed, user=user, role=Member.ROLE_OWNER)
    Member.objects.create(workspace=forbidden, user=other, role=Member.ROLE_OWNER)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/projects", HTTP_X_WORKSPACE_ID=str(forbidden.id))

    assert response.status_code == 403


@pytest.mark.django_db
def test_member_create_rejects_body_scope_mismatch(django_user_model):
    owner = django_user_model.objects.create_user(email="owner@example.com", name="Owner")
    invitee = django_user_model.objects.create_user(email="invitee@example.com", name="Invitee")
    workspace_a = Workspace.objects.create(name="A", slug="a")
    workspace_b = Workspace.objects.create(name="B", slug="b")
    Member.objects.create(workspace=workspace_a, user=owner, role=Member.ROLE_OWNER)
    Member.objects.create(workspace=workspace_b, user=owner, role=Member.ROLE_OWNER)

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.post(
        "/api/members/",
        {"workspace_id": str(workspace_b.id), "user_id": str(invitee.id), "role": Member.ROLE_MEMBER},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace_a.id),
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_daemon_viewset_is_scoped_to_workspace_binding(django_user_model):
    user = django_user_model.objects.create_user(email="daemon-owner@example.com", name="Owner")
    workspace = Workspace.objects.create(name="Daemon WS", slug="daemon-ws")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    bound = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="bound")
    unbound = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="unbound")
    DaemonWorkspaceBinding.objects.create(daemon=bound, workspace=workspace, created_by=user)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/daemons/", HTTP_X_WORKSPACE_ID=str(workspace.id))

    assert response.status_code == 200
    items = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
    ids = {item["id"] for item in items}
    assert str(bound.id) in ids
    assert str(unbound.id) not in ids


@pytest.mark.django_db
def test_agent_create_rejects_unbound_daemon(django_user_model):
    user = django_user_model.objects.create_user(email="agent-owner@example.com", name="Owner")
    workspace = Workspace.objects.create(name="Agent WS", slug="agent-security-ws")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="unbound")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/agents",
        {"name": "Bot", "provider": "claude", "model": "fake", "daemon_id": str(daemon.id)},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert response.status_code == 403
    assert not Agent.objects.filter(name="Bot").exists()


@pytest.mark.django_db
def test_existing_daemon_register_requires_existing_token():
    daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="existing")
    _token, raw = DaemonToken.issue(daemon)

    anonymous = APIClient()
    denied = anonymous.post(
        "/api/daemon/register",
        {"machine_id": str(daemon.machine_id), "device_name": "stolen"},
        format="json",
    )
    assert denied.status_code in (400, 401, 403)

    authorized = APIClient()
    authorized.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    allowed = authorized.post(
        "/api/daemon/register",
        {"machine_id": str(daemon.machine_id), "device_name": "rotated"},
        format="json",
    )
    assert allowed.status_code == 201, allowed.data
    assert allowed.data["token"].startswith("mdt_")


@pytest.mark.django_db
def test_workspace_scope_rejects_non_member_for_core_collections(django_user_model):
    user = django_user_model.objects.create_user(email="scope-user@example.com", name="Scope User")
    other = django_user_model.objects.create_user(email="scope-other@example.com", name="Scope Other")
    allowed = Workspace.objects.create(name="Allowed Core", slug="allowed-core")
    forbidden = Workspace.objects.create(name="Forbidden Core", slug="forbidden-core")
    Member.objects.create(workspace=allowed, user=user, role=Member.ROLE_OWNER)
    forbidden_member = Member.objects.create(workspace=forbidden, user=other, role=Member.ROLE_OWNER)
    forbidden_daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="forbidden-daemon")
    forbidden_agent = Agent.objects.create(
        workspace=forbidden, daemon=forbidden_daemon, name="Hidden", provider="claude"
    )
    Project.objects.create(workspace=forbidden, title="Hidden Project")
    Issue.objects.create(
        workspace=forbidden, title="Hidden Issue", creator_type="member", creator_id=forbidden_member.id
    )
    InboxItem.objects.create(
        workspace=forbidden,
        recipient_type="member",
        recipient_id=forbidden_member.id,
        type=InboxItem.Type.MENTIONED,
        title="Hidden Inbox",
    )
    Autopilot.objects.create(
        workspace=forbidden,
        title="Hidden Autopilot",
        assignee=forbidden_agent,
        created_by_type="member",
        created_by_id=forbidden_member.id,
    )
    ChatSession.objects.create(
        workspace=forbidden,
        agent=forbidden_agent,
        creator_type=ChatSession.CREATOR_MEMBER,
        creator_id=forbidden_member.id,
        title="Hidden Chat",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    for path in ("/api/members/", "/api/issues", "/api/agents", "/api/inbox", "/api/autopilots", "/api/sessions/"):
        response = client.get(path, HTTP_X_WORKSPACE_ID=str(forbidden.id))
        assert response.status_code == 403, path


@pytest.mark.django_db
def test_member_list_is_scoped_to_resolved_workspace(django_user_model):
    user = django_user_model.objects.create_user(email="multi-owner@example.com", name="Owner")
    other = django_user_model.objects.create_user(email="multi-other@example.com", name="Other")
    workspace_a = Workspace.objects.create(name="Team A", slug="team-a")
    workspace_b = Workspace.objects.create(name="Team B", slug="team-b")
    member_a = Member.objects.create(workspace=workspace_a, user=user, role=Member.ROLE_OWNER)
    Member.objects.create(workspace=workspace_b, user=user, role=Member.ROLE_OWNER)
    Member.objects.create(workspace=workspace_b, user=other, role=Member.ROLE_MEMBER)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/members/", HTTP_X_WORKSPACE_ID=str(workspace_a.id))

    assert response.status_code == 200
    items = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
    assert [item["id"] for item in items] == [str(member_a.id)]


@pytest.mark.django_db
def test_issue_create_and_comment_default_to_member_actor(django_user_model):
    user = django_user_model.objects.create_user(email="actor@example.com", name="Actor")
    workspace = Workspace.objects.create(name="Actor WS", slug="actor-ws")
    member = Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)

    client = APIClient()
    client.force_authenticate(user=user)
    issue_response = client.post(
        "/api/issues/",
        {"title": "Member-created issue"},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert issue_response.status_code == 201, issue_response.data
    assert issue_response.data["creator_type"] == "member"
    assert issue_response.data["creator_id"] == str(member.id)

    comment_response = client.post(
        f"/api/issues/{issue_response.data['id']}/comments",
        {"content": "Resolve me"},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )
    assert comment_response.status_code == 201, comment_response.data
    assert comment_response.data["author_type"] == "member"
    assert comment_response.data["author_id"] == str(member.id)

    resolve_response = client.post(
        f"/api/issues/{issue_response.data['id']}/comments/{comment_response.data['id']}/resolve",
        {},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )
    assert resolve_response.status_code == 200, resolve_response.data
    assert resolve_response.data["resolved_by_type"] == "member"
    assert resolve_response.data["resolved_by_id"] == str(member.id)


@pytest.mark.django_db
def test_agent_update_rejects_unbound_daemon(django_user_model):
    user = django_user_model.objects.create_user(email="agent-update@example.com", name="Owner")
    workspace = Workspace.objects.create(name="Agent Update WS", slug="agent-update-ws")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    bound = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="bound")
    unbound = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="unbound")
    DaemonWorkspaceBinding.objects.create(daemon=bound, workspace=workspace, created_by=user)
    agent = Agent.objects.create(workspace=workspace, daemon=bound, name="Bot", provider="claude")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.patch(
        f"/api/agents/{agent.id}",
        {"daemon_id": str(unbound.id)},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert response.status_code == 403
    agent.refresh_from_db()
    assert agent.daemon_id == bound.id


@pytest.mark.django_db
def test_chat_session_create_uses_member_actor(django_user_model):
    user = django_user_model.objects.create_user(email="chat-actor@example.com", name="Chat Actor")
    workspace = Workspace.objects.create(name="Chat Actor WS", slug="chat-actor-ws")
    member = Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    agent = Agent.objects.create(workspace=workspace, name="Chat Bot", provider="claude")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/sessions/",
        {"agent": str(agent.id), "title": "Hello"},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert response.status_code == 201, response.data
    assert response.data["creator_type"] == "member"
    assert response.data["creator_id"] == str(member.id)


@pytest.mark.django_db
def test_daemon_task_status_requires_token_and_returns_bound_task(django_user_model):
    user = django_user_model.objects.create_user(email="daemon-status@example.com", name="Daemon Status")
    workspace = Workspace.objects.create(name="Daemon Status WS", slug="daemon-status-ws")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="status-daemon")
    _token, raw = DaemonToken.issue(daemon)
    DaemonWorkspaceBinding.objects.create(daemon=daemon, workspace=workspace, created_by=user)
    agent = Agent.objects.create(workspace=workspace, daemon=daemon, name="Status Bot", provider="claude")
    issue = Issue.objects.create(
        workspace=workspace, title="Status task", creator_type="member", creator_id=workspace.members.first().id
    )
    from agents.models import Task

    task = Task.objects.create(agent=agent, daemon=daemon, issue=issue)

    anonymous = APIClient()
    denied = anonymous.get(f"/api/daemon/tasks/{task.id}/status")
    assert denied.status_code in (401, 403)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    response = client.get(f"/api/daemon/tasks/{task.id}/status")
    assert response.status_code == 200, response.data
    assert response.data["id"] == str(task.id)


@pytest.mark.django_db
def test_agent_create_requires_daemon_id(django_user_model):
    user = django_user_model.objects.create_user(email="agent-required@example.com", name="Owner")
    workspace = Workspace.objects.create(name="Agent Required WS", slug="agent-required-ws")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/agents",
        {"name": "No Daemon Bot", "provider": "claude", "model": "fake"},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert response.status_code == 400
    assert "daemon_id" in response.data


@pytest.mark.django_db
def test_daemon_register_with_stale_token_rejects_new_machine_id():
    daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="old")
    _token, raw = DaemonToken.issue(daemon)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    response = client.post(
        "/api/daemon/register",
        {"machine_id": str(uuid.uuid4()), "device_name": "unexpected-new"},
        format="json",
    )

    assert response.status_code == 400
    assert Daemon.objects.count() == 1


@pytest.mark.django_db
@override_settings(BODIAGENT_ALLOW_ANONYMOUS_DAEMON_REGISTER=True)
def test_daemon_first_register_allows_missing_token():
    client = APIClient()
    response = client.post(
        "/api/daemon/register",
        {"machine_id": str(uuid.uuid4()), "device_name": "first"},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["token"].startswith("mdt_")
    assert Daemon.objects.count() == 1


@pytest.mark.django_db
def test_daemon_first_register_requires_setup_unless_explicitly_allowed():
    client = APIClient()
    response = client.post(
        "/api/daemon/register",
        {"machine_id": str(uuid.uuid4()), "device_name": "anonymous"},
        format="json",
    )

    assert response.status_code == 400
    assert Daemon.objects.count() == 0


@pytest.mark.django_db
def test_daemon_setup_registers_binds_and_returns_daemon_token(django_user_model):
    user = django_user_model.objects.create_user(email="daemon-setup@example.com", name="Owner")
    workspace = Workspace.objects.create(name="Daemon Setup WS", slug="daemon-setup-ws")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)

    client = APIClient()
    client.force_authenticate(user=user)
    machine_id = uuid.uuid4()
    response = client.post(
        "/api/daemons/setup/",
        {
            "workspace_id": str(workspace.id),
            "machine_id": str(machine_id),
            "device_name": "local-dev",
            "providers": ["claude"],
        },
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert response.status_code == 201, response.data
    assert response.data["token"].startswith("mdt_")
    daemon = Daemon.objects.get(machine_id=machine_id)
    assert daemon.available_providers == ["claude"]
    assert DaemonWorkspaceBinding.objects.filter(daemon=daemon, workspace=workspace, revoked_at__isnull=True).exists()

    list_response = client.get("/api/daemons/", HTTP_X_WORKSPACE_ID=str(workspace.id))
    if isinstance(list_response.data, dict):
        items = list_response.data.get("results", list_response.data)
    else:
        items = list_response.data
    assert str(daemon.id) in {item["id"] for item in items}


@pytest.mark.django_db
def test_daemon_bind_accepts_user_auth_plus_daemon_token_body(django_user_model):
    user = django_user_model.objects.create_user(email="daemon-bind@example.com", name="Owner")
    workspace = Workspace.objects.create(name="Daemon Bind WS", slug="daemon-bind-ws")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="claimable")
    _token, raw = DaemonToken.issue(daemon)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/daemons/bind/",
        {"daemon_token": raw},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert response.status_code == 201, response.data
    assert DaemonWorkspaceBinding.objects.filter(daemon=daemon, workspace=workspace, revoked_at__isnull=True).exists()


@pytest.mark.django_db
def test_daemon_bind_rejects_mismatched_daemon_token_claims(django_user_model):
    user = django_user_model.objects.create_user(email="daemon-bind-mismatch@example.com", name="Owner")
    workspace = Workspace.objects.create(name="Daemon Bind Mismatch WS", slug="daemon-bind-mismatch-ws")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="body")
    other_daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="header")
    _token, raw = DaemonToken.issue(daemon)
    _other_token, other_raw = DaemonToken.issue(other_daemon)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/daemons/bind/",
        {"daemon_token": raw},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
        HTTP_X_DAEMON_TOKEN=other_raw,
    )

    assert response.status_code == 400
    assert not DaemonWorkspaceBinding.objects.filter(daemon=daemon, workspace=workspace).exists()
    assert not DaemonWorkspaceBinding.objects.filter(daemon=other_daemon, workspace=workspace).exists()


@pytest.mark.django_db
def test_daemon_setup_rejects_machine_bound_to_unauthorized_workspace(django_user_model):
    owner = django_user_model.objects.create_user(email="daemon-owner-a@example.com", name="Owner A")
    other_owner = django_user_model.objects.create_user(email="daemon-owner-b@example.com", name="Owner B")
    workspace = Workspace.objects.create(name="Daemon Setup A", slug="daemon-setup-a")
    other_workspace = Workspace.objects.create(name="Daemon Setup B", slug="daemon-setup-b")
    Member.objects.create(workspace=workspace, user=owner, role=Member.ROLE_OWNER)
    Member.objects.create(workspace=other_workspace, user=other_owner, role=Member.ROLE_OWNER)
    daemon = Daemon.objects.create(machine_id=uuid.uuid4(), device_name="other-bound")
    DaemonWorkspaceBinding.objects.create(daemon=daemon, workspace=other_workspace, created_by=other_owner)

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.post(
        "/api/daemons/setup/",
        {
            "workspace_id": str(workspace.id),
            "machine_id": str(daemon.machine_id),
            "device_name": "local-dev",
            "providers": ["claude"],
        },
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert response.status_code == 403
    assert not DaemonWorkspaceBinding.objects.filter(daemon=daemon, workspace=workspace).exists()


@pytest.mark.django_db
def test_issue_create_assigns_incrementing_workspace_numbers(django_user_model):
    user = django_user_model.objects.create_user(email="issue-create@example.com", name="Issue Creator")
    workspace = Workspace.objects.create(name="Issue Create", slug="issue-create")
    member = Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    Issue.objects.create(
        workspace=workspace,
        number=1,
        title="Existing issue",
        creator_type="member",
        creator_id=member.id,
    )

    client = APIClient()
    client.force_authenticate(user=user)
    first = client.post(
        "/api/issues",
        {"title": "Created through API", "status": "todo", "priority": "medium"},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )
    second = client.post(
        "/api/issues",
        {"title": "Second through API", "status": "backlog", "priority": "low"},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    workspace.refresh_from_db()
    assert first.data["number"] == 2
    assert second.data["number"] == 3
    assert workspace.issue_counter == 3
    assert Issue.objects.filter(workspace=workspace).count() == 3


@pytest.mark.django_db
def test_issue_create_numbers_are_workspace_scoped(django_user_model):
    user = django_user_model.objects.create_user(email="issue-scope@example.com", name="Issue Scope")
    workspace_a = Workspace.objects.create(name="Issue Scope A", slug="issue-scope-a")
    workspace_b = Workspace.objects.create(name="Issue Scope B", slug="issue-scope-b")
    member_a = Member.objects.create(workspace=workspace_a, user=user, role=Member.ROLE_OWNER)
    Member.objects.create(workspace=workspace_b, user=user, role=Member.ROLE_OWNER)
    Issue.objects.create(
        workspace=workspace_a,
        number=9,
        title="Existing A",
        creator_type="member",
        creator_id=member_a.id,
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/issues",
        {"title": "Created in B"},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace_b.id),
    )

    workspace_b.refresh_from_db()
    assert response.status_code == 201, response.data
    assert response.data["number"] == 1
    assert workspace_b.issue_counter == 1
