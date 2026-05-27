"""Database and browser-auth helpers for E2E specs."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.db.models import Max

from accounts.models import Daemon, DaemonWorkspaceBinding, Member, PersonalAccessToken, Workspace
from agents.models import Agent
from autopilots.models import Autopilot, AutopilotTrigger
from chat.models import ChatSession
from inbox.models import Activity, InboxItem
from issues.models import Issue
from projects.models import Project


@dataclass(frozen=True)
class BrowserUser:
    user: object
    workspace: Workspace
    member: Member


def unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def create_browser_user(prefix: str = "e2e") -> BrowserUser:
    user_model = get_user_model()
    suffix = uuid4().hex[:10]
    user = user_model.objects.create_user(
        email=f"{prefix}-{suffix}@example.com",
        password="admin123",
        name=f"E2E {suffix}",
    )
    workspace = Workspace.objects.create(name=f"E2E Workspace {suffix}", slug=unique_slug(prefix))
    member = Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    return BrowserUser(user=user, workspace=workspace, member=member)


def create_agent(workspace: Workspace, name: str = "E2E Agent") -> Agent:
    daemon = Daemon.objects.create(
        machine_id=uuid4(),
        device_name=f"daemon-{uuid4().hex[:6]}",
        available_providers=["claude"],
    )
    DaemonWorkspaceBinding.objects.create(daemon=daemon, workspace=workspace)
    return Agent.objects.create(
        workspace=workspace,
        daemon=daemon,
        name=name,
        provider="claude",
        model="claude-sonnet-4",
        status=Agent.Status.ACTIVE,
        visibility=Agent.Visibility.WORKSPACE,
        max_concurrent_tasks=3,
    )


def create_issue(workspace: Workspace, member: Member, **overrides: object) -> Issue:
    next_number = (
        Issue.objects.filter(workspace=workspace).aggregate(max_number=Max("number"))["max_number"] or 0
    ) + 1
    defaults = {
        "workspace": workspace,
        "number": overrides.pop("number", next_number),
        "title": "E2E seeded issue",
        "description": "Seeded issue description",
        "status": Issue.Status.BACKLOG,
        "priority": Issue.Priority.MEDIUM,
        "creator_type": "member",
        "creator_id": member.id,
        "position": 0,
    }
    defaults.update(overrides)
    return Issue.objects.create(**defaults)


def create_project(workspace: Workspace, title: str = "E2E Project") -> Project:
    return Project.objects.create(workspace=workspace, title=title, description="Project from e2e", priority="medium")


def create_autopilot(workspace: Workspace, member: Member, agent: Agent) -> Autopilot:
    autopilot = Autopilot.objects.create(
        workspace=workspace,
        title="E2E Autopilot",
        description="Runs from the browser suite",
        assignee=agent,
        status=Autopilot.Status.ACTIVE,
        execution_mode=Autopilot.ExecutionMode.RUN_ONLY,
        issue_title_template="E2E {{ date }}",
        created_by_type="member",
        created_by_id=member.id,
    )
    AutopilotTrigger.objects.create(
        autopilot=autopilot,
        kind=AutopilotTrigger.Kind.SCHEDULE,
        enabled=True,
        cron_expression="0 9 * * *",
        timezone="Asia/Shanghai",
        label="Daily",
    )
    return autopilot


def create_chat_session(workspace: Workspace, member: Member, agent: Agent) -> ChatSession:
    return ChatSession.objects.create(
        workspace=workspace,
        agent=agent,
        creator_type=ChatSession.CREATOR_MEMBER,
        creator_id=member.id,
        title="E2E Chat",
        context={},
    )



def create_inbox_item(
    workspace: Workspace,
    member: Member,
    title: str = "E2E Inbox Item",
    *,
    body: str = "Inbox item from e2e",
    issue: Issue | None = None,
    read: bool = False,
    archived: bool = False,
    inbox_type: str = InboxItem.Type.NEW_COMMENT,
    severity: str = InboxItem.Severity.INFO,
) -> InboxItem:
    return InboxItem.objects.create(
        workspace=workspace,
        recipient_type=InboxItem.RecipientType.MEMBER,
        recipient_id=member.id,
        actor_type=InboxItem.ActorType.SYSTEM,
        actor_id=None,
        type=inbox_type,
        severity=severity,
        issue_id=issue.id if issue else None,
        title=title,
        body=body,
        read=read,
        archived=archived,
    )

def create_activity(workspace: Workspace, issue: Issue, member: Member, action: str = "updated") -> Activity:
    return Activity.objects.create(
        workspace=workspace,
        issue_id=issue.id,
        actor_type="member",
        actor_id=member.id,
        action=action,
        details={"source": "e2e"},
    )


def create_cli_token(user: object, name: str = "E2E Token") -> PersonalAccessToken:
    token, _raw = PersonalAccessToken.issue(user, name=name, prefix="cli_")
    return token


def force_login_context(context, live_server_url: str, user: object, workspace: Workspace) -> None:
    """Create an authenticated browser state from Django's session cookie."""
    session_store = import_module(settings.SESSION_ENGINE).SessionStore
    session = session_store()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    context.add_cookies([
        {
            "name": settings.SESSION_COOKIE_NAME,
            "value": session.session_key,
            "url": live_server_url,
            "httpOnly": True,
            "sameSite": "Lax",
        }
    ])
    context.add_init_script(
        f"""() => {{
            window.localStorage.setItem('bodiagent_token', 'e2e-session-token');
            window.localStorage.setItem('bodiagent_refresh', 'e2e-refresh-token');
            window.localStorage.setItem('bodiagent_workspace_id', '{workspace.id}');
        }}"""
    )





def login_context_via_api(context, live_server_url: str, browser_user: BrowserUser) -> None:
    """Authenticate a BrowserContext against the running HTTP server.

    This is required for ASGI/Daphne browser tests because the WebSocket
    AuthMiddleware must consume the same session cookie shape emitted by the
    server under test, regardless of prior imports or session-engine caching.
    """
    response = context.request.post(
        live_server_url + "/api/auth/login",
        data={"email": browser_user.user.email, "password": "admin123"},
        headers={"Accept": "application/json"},
    )
    assert response.ok, f"ASGI browser login failed: {response.status} {response.text()}"
    context.add_init_script(
        f"""() => {{
            window.localStorage.setItem('bodiagent_token', 'e2e-session-token');
            window.localStorage.setItem('bodiagent_refresh', 'e2e-refresh-token');
            window.localStorage.setItem('bodiagent_workspace_id', '{browser_user.workspace.id}');
        }}"""
    )


def workspace_headers(workspace: Workspace) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace.id)}
