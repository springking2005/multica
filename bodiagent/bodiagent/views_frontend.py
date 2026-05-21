"""Simple template-serving views for the frontend shell.

These views handle the "page" entrypoints that serve HTML templates.
Real data is loaded client-side via HTMX calls to the API.
"""

from __future__ import annotations

from uuid import UUID

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from accounts.models import Member


def _frontend_context(request: HttpRequest, **extra: object) -> dict[str, object]:
    """Build common context for template shells that call workspace-scoped APIs."""
    memberships = []
    membership: Member | None = None

    if request.user.is_authenticated:
        memberships = list(request.user.memberships.select_related("workspace").order_by("created_at"))
        memberships_by_workspace = {str(item.workspace_id): item for item in memberships}

        requested_workspace_id = request.GET.get("workspace_id")
        if requested_workspace_id in memberships_by_workspace:
            request.session["current_workspace_id"] = requested_workspace_id
            membership = memberships_by_workspace[requested_workspace_id]

        if membership is None:
            session_workspace_id = request.session.get("current_workspace_id")
            if session_workspace_id in memberships_by_workspace:
                membership = memberships_by_workspace[session_workspace_id]

        if membership is None and memberships:
            membership = memberships[0]
            request.session["current_workspace_id"] = str(membership.workspace_id)

    workspace = membership.workspace if membership is not None else None
    workspace_id = str(workspace.id) if workspace is not None else ""

    context: dict[str, object] = {
        "workspaces": [item.workspace for item in memberships],
        "current_workspace": workspace,
        "current_workspace_id": workspace_id,
        "current_user_id": str(request.user.id) if request.user.is_authenticated else "",
        "current_member_id": str(membership.id) if membership is not None else "",
    }
    context.update(extra)
    return context


def home(request: HttpRequest) -> HttpResponse:
    """Redirect authenticated users to dashboard, anonymous to login."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("accounts-login")


def dashboard(request: HttpRequest) -> HttpResponse:
    """Serve the dashboard shell with current workspace context."""
    return render(request, "accounts/dashboard.html", _frontend_context(request))


def issues_board(request: HttpRequest) -> HttpResponse:
    """Serve the issue board shell with current workspace context."""
    return render(request, "issues/board.html", _frontend_context(request))


def my_issues(request: HttpRequest) -> HttpResponse:
    """Serve the current user's assigned issues page."""
    return render(request, "issues/my_issues.html", _frontend_context(request))


def inbox(request: HttpRequest) -> HttpResponse:
    """Serve the inbox shell with current workspace context."""
    return render(request, "inbox/list.html", _frontend_context(request))


def settings(request: HttpRequest) -> HttpResponse:
    """Serve the settings profile shell with current workspace context."""
    return render(request, "settings/profile.html", _frontend_context(request))


def issue_detail(request: HttpRequest, issue_id: UUID) -> HttpResponse:
    """Serve the issue detail page shell. Data loaded via HTMX."""
    return render(
        request,
        "issues/detail.html",
        _frontend_context(request, issue_id=str(issue_id)),
    )


def agents(request: HttpRequest) -> HttpResponse:
    """Serve the agent management page shell."""
    return render(request, "agents/list.html", _frontend_context(request))


def agent_detail(request: HttpRequest, agent_id: UUID) -> HttpResponse:
    """Serve the agent detail page shell."""
    return render(request, "agents/detail.html", _frontend_context(request, agent_id=str(agent_id)))


def chat_detail(request: HttpRequest, session_id: UUID | None = None) -> HttpResponse:
    """Serve the chat page shell."""
    return render(
        request,
        "chat/detail.html",
        _frontend_context(request, session_id=str(session_id) if session_id else ""),
    )


def projects(request: HttpRequest) -> HttpResponse:
    """Serve the project management page shell."""
    return render(request, "projects/list.html", _frontend_context(request))


def project_detail(request: HttpRequest, project_id: UUID) -> HttpResponse:
    """Serve the project detail page shell."""
    return render(request, "projects/detail.html", _frontend_context(request, project_id=str(project_id)))


def autopilots(request: HttpRequest) -> HttpResponse:
    """Serve the autopilot management page shell."""
    return render(request, "autopilots/list.html", _frontend_context(request))


def tokens(request: HttpRequest) -> HttpResponse:
    """Serve the token management page shell."""
    return render(request, "settings/tokens.html", _frontend_context(request))
