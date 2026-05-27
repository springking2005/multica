"""Workspace and daemon boundary helpers for API views."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.utils import timezone
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
)

from .models import Daemon, DaemonToken, DaemonWorkspaceBinding, Member, hash_token


def _parse_uuid(raw: Any, field_name: str) -> UUID:
    try:
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise ValidationError({field_name: f"{field_name} must be a valid UUID."}) from exc


def resolve_workspace_id(request, required: bool = True) -> UUID | None:
    raw_workspace_id = (
        getattr(request, "workspace_id", None)
        or request.headers.get("X-Workspace-ID")
        or request.query_params.get("ws_id")
    )
    if not raw_workspace_id:
        if required:
            raise ValidationError({"workspace_id": "X-Workspace-ID header or ws_id query parameter is required."})
        return None
    workspace_id = _parse_uuid(raw_workspace_id, "workspace_id")
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        raise NotAuthenticated("Authentication is required.")
    if not Member.objects.filter(workspace_id=workspace_id, user=user).exists():
        raise PermissionDenied("Workspace membership is required.")
    return workspace_id


def resolve_workspace_member(request, workspace_id: UUID | None = None) -> Member:
    resolved_workspace_id = workspace_id or resolve_workspace_id(request)
    member = (
        Member.objects.filter(workspace_id=resolved_workspace_id, user=request.user)
        .select_related("workspace", "user")
        .first()
    )
    if member is None:
        raise PermissionDenied("Workspace membership is required.")
    return member


def require_workspace_admin(request, workspace_id: UUID | None = None) -> Member:
    member = resolve_workspace_member(request, workspace_id)
    if member.role not in (Member.ROLE_OWNER, Member.ROLE_ADMIN):
        raise PermissionDenied("Admin role required.")
    return member


def validate_actor_ref(actor_type: str | None, actor_id: Any, workspace_id: UUID, *, required: bool = False):
    if not actor_type and not actor_id and not required:
        return
    if not actor_type or not actor_id:
        raise ValidationError({"actor": "actor_type and actor_id are required together."})
    parsed_actor_id = _parse_uuid(actor_id, "actor_id")
    if actor_type == "member":
        member = Member.objects.filter(id=parsed_actor_id, workspace_id=workspace_id).first()
        if member is None:
            raise PermissionDenied("Actor member must belong to the workspace.")
        return member
    if actor_type == "agent":
        from agents.models import Agent

        agent = Agent.objects.filter(id=parsed_actor_id, workspace_id=workspace_id).first()
        if agent is None:
            raise PermissionDenied("Actor agent must belong to the workspace.")
        return agent
    if actor_type == "system" and not required:
        return None
    raise ValidationError({"actor_type": "Unsupported actor type."})


def validate_issue_id(issue_id: Any, workspace_id: UUID, *, field_name: str = "issue_id", required: bool = False):
    if not issue_id:
        if required:
            raise ValidationError({field_name: f"{field_name} is required."})
        return None
    parsed_issue_id = _parse_uuid(issue_id, field_name)
    from issues.models import Issue

    issue = Issue.objects.filter(id=parsed_issue_id, workspace_id=workspace_id).first()
    if issue is None:
        raise PermissionDenied("Issue must belong to the workspace.")
    return issue


def validate_project_id(project_id: Any, workspace_id: UUID, *, field_name: str = "project_id", required: bool = False):
    if not project_id:
        if required:
            raise ValidationError({field_name: f"{field_name} is required."})
        return None
    parsed_project_id = _parse_uuid(project_id, field_name)
    from projects.models import Project

    project = Project.objects.filter(id=parsed_project_id, workspace_id=workspace_id).first()
    if project is None:
        raise PermissionDenied("Project must belong to the workspace.")
    return project


def validate_daemon_binding(daemon_id: Any, workspace_id: UUID, *, required: bool = False) -> Daemon | None:
    if not daemon_id:
        if required:
            raise ValidationError({"daemon_id": "daemon_id is required."})
        return None
    parsed_daemon_id = _parse_uuid(daemon_id, "daemon_id")
    binding = (
        DaemonWorkspaceBinding.objects.filter(
            daemon_id=parsed_daemon_id,
            workspace_id=workspace_id,
            revoked_at__isnull=True,
        )
        .select_related("daemon")
        .first()
    )
    if binding is None:
        raise PermissionDenied("Daemon is not bound to this workspace.")
    return binding.daemon


def validate_skill_ids(skill_ids: list[UUID], workspace_id: UUID) -> None:
    if not skill_ids:
        return
    from agents.models import Skill

    found = set(Skill.objects.filter(id__in=skill_ids, workspace_id=workspace_id).values_list("id", flat=True))
    missing = set(skill_ids) - found
    if missing:
        raise PermissionDenied("All skills must belong to the workspace.")


def validate_pin_target(item_type: str, item_id: Any, workspace_id: UUID) -> None:
    parsed_item_id = _parse_uuid(item_id, "item_id")
    if item_type == "issue":
        from issues.models import Issue

        if Issue.objects.filter(id=parsed_item_id, workspace_id=workspace_id).exists():
            return
    elif item_type == "project":
        from projects.models import Project

        if Project.objects.filter(id=parsed_item_id, workspace_id=workspace_id).exists():
            return
    else:
        raise ValidationError({"item_type": "Unsupported pin item type."})
    raise PermissionDenied("Pinned item must belong to the workspace.")


def get_bearer_token(request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise NotAuthenticated("Daemon bearer token is required.")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise NotAuthenticated("Daemon bearer token is required.")
    return token



def resolve_daemon_from_token(raw_token: str) -> Daemon:
    token = (
        DaemonToken.objects.filter(token_hash=hash_token(raw_token), expires_at__gt=timezone.now())
        .select_related("daemon")
        .first()
    )
    if token is None:
        raise AuthenticationFailed("Invalid daemon token.")
    return token.daemon


def resolve_daemon_from_claim(request) -> Daemon:
    candidates = [
        getattr(request, "data", {}).get("daemon_token"),
        request.headers.get("X-Daemon-Token"),
        request.headers.get("X-BodiAgent-Daemon-Token"),
    ]
    tokens = [str(token).strip() for token in candidates if token]
    if not tokens:
        raise NotAuthenticated("daemon_token or X-Daemon-Token is required.")
    if len(set(tokens)) > 1:
        raise ValidationError({"daemon_token": "Daemon token claims must match when provided in multiple places."})
    return resolve_daemon_from_token(tokens[0])


def resolve_daemon_from_request(request) -> Daemon:
    raw_token = get_bearer_token(request)
    return resolve_daemon_from_token(raw_token)


def validate_request_daemon_id(request, daemon: Daemon, field_name: str = "daemon_id") -> None:
    raw = getattr(request, "data", {}).get(field_name)
    if not raw:
        return
    parsed_daemon_id = _parse_uuid(raw, field_name)
    if parsed_daemon_id != daemon.id:
        raise PermissionDenied("Daemon token does not match daemon_id.")


def bind_daemon_to_workspace(daemon: Daemon, workspace_id: UUID, created_by=None) -> DaemonWorkspaceBinding:
    defaults = {"revoked_at": None}
    if created_by is not None:
        defaults["created_by"] = created_by
    binding, _ = DaemonWorkspaceBinding.objects.update_or_create(
        daemon=daemon, workspace_id=workspace_id, defaults=defaults
    )
    return binding
