"""Service helpers for agent task dispatch and issue reply side effects."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Agent, Task

ACTIVE_TASK_STATUSES = (Task.Status.QUEUED, Task.Status.DISPATCHED, Task.Status.RUNNING)
TERMINAL_ISSUE_STATUSES = {"done", "cancelled"}
MENTION_LINK_RE = re.compile(r"mention://agent/([0-9a-fA-F-]{36})")
RAW_AGENT_MENTION_RE = re.compile(r"@agent:([0-9a-fA-F-]{36})")


def _find_ready_agent(issue, agent_id) -> Agent | None:
    agent = Agent.objects.filter(
        id=agent_id,
        workspace_id=issue.workspace_id,
        status=Agent.Status.ACTIVE,
    ).first()
    if agent is None or agent.daemon_id is None:
        return None
    return agent


def _get_ready_agent(issue, agent_id) -> Agent:
    agent = _find_ready_agent(issue, agent_id)
    if agent is None:
        raise ValidationError({"assignee_id": "Agent must belong to the workspace, be active, and bind to a daemon."})
    return agent


def _create_or_get_active_task(
    issue,
    agent: Agent,
    *,
    trigger_summary: str = "",
    trigger_comment=None,
    cancel_other_agents: bool = True,
    dedupe_existing: bool = True,
    force_fresh_session: bool = False,
) -> Task:
    with transaction.atomic():
        issue.__class__.objects.select_for_update().get(pk=issue.pk)
        active_tasks = Task.objects.select_for_update().filter(
            issue=issue,
            status__in=ACTIVE_TASK_STATUSES,
        )
        if cancel_other_agents:
            active_tasks.exclude(agent=agent).update(
                status=Task.Status.CANCELLED,
                completed_at=timezone.now(),
                updated_at=timezone.now(),
            )
        if trigger_comment is not None:
            existing_for_comment = (
                active_tasks.filter(agent=agent, trigger_comment=trigger_comment)
                .order_by("created_at")
                .first()
            )
            if existing_for_comment:
                return existing_for_comment
        existing = active_tasks.filter(agent=agent).order_by("created_at").first()
        if existing and dedupe_existing:
            return existing
        return Task.objects.create(
            agent=agent,
            daemon=agent.daemon,
            issue=issue,
            trigger_summary=trigger_summary,
            trigger_comment=trigger_comment,
            force_fresh_session=force_fresh_session,
        )


def enqueue_issue_assignment_task(issue, *, trigger_summary: str = "") -> Task | None:
    """Queue daemon work when an issue is assigned to an agent.

    The helper is idempotent for active tasks so repeated PATCH/batch updates do
    not dispatch duplicate daemon work for the same issue-agent pair.
    """
    if issue.status in TERMINAL_ISSUE_STATUSES:
        return None
    if issue.assignee_type != "agent" or not issue.assignee_id:
        return None
    agent = _get_ready_agent(issue, issue.assignee_id)
    return _create_or_get_active_task(
        issue,
        agent,
        trigger_summary=trigger_summary,
        cancel_other_agents=True,
    )


def cancel_active_tasks_for_issue(issue, *, agent: Agent | None = None, reason: str = "") -> int:
    """Cancel queued/dispatched/running tasks for an issue, optionally scoped to one agent."""
    queryset = Task.objects.filter(issue=issue, status__in=ACTIVE_TASK_STATUSES)
    if agent is not None:
        queryset = queryset.filter(agent=agent)
    return queryset.update(
        status=Task.Status.CANCELLED,
        failure_reason=reason,
        completed_at=timezone.now(),
        updated_at=timezone.now(),
    )


def reconcile_issue_task_state(
    issue,
    *,
    old_assignee_type: str | None = None,
    old_assignee_id=None,
    old_status: str | None = None,
) -> Task | None:
    """Keep issue assignment/status changes in sync with active daemon tasks."""
    assignee_changed = old_assignee_type != issue.assignee_type or old_assignee_id != issue.assignee_id
    status_changed = old_status is not None and old_status != issue.status

    if issue.status in TERMINAL_ISSUE_STATUSES:
        cancel_active_tasks_for_issue(issue, reason=f"Issue moved to terminal status: {issue.status}.")
        return None

    if assignee_changed and issue.assignee_type != "agent":
        cancel_active_tasks_for_issue(issue, reason="Issue was unassigned from agent.")
        return None

    if assignee_changed:
        cancel_active_tasks_for_issue(issue, reason="Issue was reassigned to another agent.")

    if issue.assignee_type != "agent" or not issue.assignee_id:
        return None

    should_enqueue = False
    trigger_summary = ""
    if assignee_changed:
        should_enqueue = True
        trigger_summary = "Issue assigned to agent. Review the issue context and produce the requested work."
    elif status_changed and old_status in {"backlog", *TERMINAL_ISSUE_STATUSES}:
        should_enqueue = True
        trigger_summary = (
            f"Issue status changed from {old_status} to {issue.status}. "
            "Start or resume the assigned work."
        )

    if should_enqueue:
        return enqueue_issue_assignment_task(issue, trigger_summary=trigger_summary)
    return None


def enqueue_issue_comment_task(issue, comment) -> Task | None:
    """Queue a follow-up task for the assigned agent when a member comments."""
    if comment.author_type == "agent" and comment.author_id == issue.assignee_id:
        return None
    if issue.assignee_type != "agent" or not issue.assignee_id or issue.status in TERMINAL_ISSUE_STATUSES:
        return None
    agent = _find_ready_agent(issue, issue.assignee_id)
    if agent is None:
        return None
    return _create_or_get_active_task(
        issue,
        agent,
        trigger_summary="New issue comment requires agent follow-up.",
        trigger_comment=comment,
        cancel_other_agents=False,
        dedupe_existing=False,
    )


def _mentioned_agent_ids(content: str, workspace_id) -> list[UUID]:
    ids: list[UUID] = []
    seen: set[UUID] = set()

    def add(raw: str) -> None:
        try:
            value = UUID(str(raw))
        except (TypeError, ValueError):
            return
        if value not in seen:
            seen.add(value)
            ids.append(value)

    for pattern in (MENTION_LINK_RE, RAW_AGENT_MENTION_RE):
        for match in pattern.finditer(content or ""):
            add(match.group(1))

    mentioned_text = content or ""
    if "@" in mentioned_text:
        for agent in Agent.objects.filter(workspace_id=workspace_id, status=Agent.Status.ACTIVE):
            token = f"@{agent.name}"
            if re.search(rf"(?<!\w){re.escape(token)}(?![\w\-.\u4e00-\u9fff])", mentioned_text):
                add(str(agent.id))
    return ids


def enqueue_issue_mention_tasks(issue, comment) -> list[Task]:
    """Queue tasks for agents explicitly mentioned in a comment."""
    tasks: list[Task] = []
    if issue.status in TERMINAL_ISSUE_STATUSES:
        return tasks
    for agent_id in _mentioned_agent_ids(comment.content, issue.workspace_id):
        if comment.author_type == "agent" and comment.author_id == agent_id:
            continue
        agent = _find_ready_agent(issue, agent_id)
        if agent is None:
            continue
        tasks.append(
            _create_or_get_active_task(
                issue,
                agent,
                trigger_summary=(
                    "You were mentioned in an issue comment. "
                    "Review the issue and respond or act as needed."
                ),
                trigger_comment=comment,
                cancel_other_agents=False,
                dedupe_existing=False,
            )
        )
    return tasks


def rerun_issue_task(issue) -> Task:
    """Cancel current active work and enqueue a fresh session for the assigned agent."""
    if issue.assignee_type != "agent" or not issue.assignee_id:
        raise ValidationError({"assignee_id": "Issue must be assigned to an active agent before rerun."})
    if issue.status in TERMINAL_ISSUE_STATUSES:
        raise ValidationError({"status": "Cannot rerun a terminal issue."})
    agent = _get_ready_agent(issue, issue.assignee_id)
    cancel_active_tasks_for_issue(issue, agent=agent, reason="Issue task rerun requested.")
    return Task.objects.create(
        agent=agent,
        daemon=agent.daemon,
        issue=issue,
        trigger_summary="Rerun requested for this issue. Start a fresh session and reprocess the full issue context.",
        force_fresh_session=True,
    )


def extract_task_summary(result: dict[str, Any]) -> str:
    """Return the human-visible summary from a daemon completion payload."""
    summary = result.get("summary") if isinstance(result, dict) else ""
    if summary is None:
        return ""
    if isinstance(summary, str):
        return summary.strip()
    return str(summary).strip()


def complete_task_with_result(task: Task, *, result: dict[str, Any], branch_name: str = "") -> Task:
    """Mark an active task complete and publish the daemon summary once as an issue comment."""
    with transaction.atomic():
        locked_task = Task.objects.select_for_update().select_related("agent", "issue").get(pk=task.pk)
        if locked_task.status != Task.Status.RUNNING:
            raise ValidationError({"status": "Only running tasks can be completed."})
        locked_task.status = Task.Status.COMPLETED
        locked_task.result = result
        locked_task.branch_name = branch_name
        locked_task.completed_at = timezone.now()
        locked_task.save(update_fields=["status", "result", "branch_name", "completed_at", "updated_at"])
        publish_task_completion_comment(locked_task, extract_task_summary(locked_task.result))
    task.refresh_from_db()
    return task


def publish_task_completion_comment(task: Task, summary: str) -> None:
    """Persist a completed task summary as a visible issue comment from the agent."""
    if not task.issue_id or not summary:
        return

    from issues.models import Comment, Issue

    Comment.objects.create(
        issue_id=task.issue_id,
        workspace_id=task.agent.workspace_id,
        author_type=Comment.AuthorType.AGENT,
        author_id=task.agent_id,
        content=summary,
        type=Comment.Type.COMMENT,
    )
    Issue.objects.filter(id=task.issue_id, first_executed_at__isnull=True).update(
        first_executed_at=timezone.now()
    )
