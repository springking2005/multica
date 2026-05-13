"""Simple template-serving views for the frontend shell.

These views handle the "page" entrypoints that serve HTML templates.
Real data is loaded client-side via HTMX calls to the API.
"""

from __future__ import annotations

from uuid import UUID

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render


def _frontend_context(request: HttpRequest, **extra: object) -> dict[str, object]:
    """Build common context for template shells that call workspace-scoped APIs."""
    workspace_id = getattr(request, "workspace_id", None)
    workspace = None
    if request.user.is_authenticated:
        membership = request.user.memberships.select_related("workspace").order_by("created_at").first()
        if membership is not None:
            workspace = membership.workspace
            workspace_id = workspace_id or str(workspace.id)

    context: dict[str, object] = {
        "current_workspace": workspace,
        "current_workspace_id": workspace_id or "",
        "current_user_id": str(request.user.id) if request.user.is_authenticated else "",
        "current_member_id": str(membership.id) if request.user.is_authenticated and membership is not None else "",
    }
    context.update(extra)
    return context


def home(request: HttpRequest) -> HttpResponse:
    """Redirect authenticated users to dashboard, anonymous to login."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("accounts-login")


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


def autopilots(request: HttpRequest) -> HttpResponse:
    """Serve the autopilot management page shell."""
    return render(request, "autopilots/list.html", _frontend_context(request))


def tokens(request: HttpRequest) -> HttpResponse:
    """Serve the token management page shell."""
    return render(request, "settings/tokens.html", _frontend_context(request))
