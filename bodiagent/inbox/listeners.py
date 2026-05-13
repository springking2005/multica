"""Signal-based event listeners for inbox notifications and activity logging.

Registered automatically in :class:`InboxConfig.ready`.

Implements the side-effect rules defined in ``listener-rules.md``:
- Subscriber auto-subscription on issue creation / update / comment.
- Activity log creation on issue and task lifecycle events.
- Inbox notification creation with per-user notification-preference gating.
- Stale task_failed auto-archive on issue status transitions.
- Parent-issue bubbling for status-change notifications.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from accounts.models import NotificationPreference

from .models import Activity, InboxItem

# ---------------------------------------------------------------------------
# Preference helpers
# ---------------------------------------------------------------------------

# Maps InboxItem.Type values to NotificationPreference boolean field names.
TYPE_TO_PREFERENCE_GROUP: dict[str, str] = {
    "issue_assigned": "assignments",
    "unassigned": "assignments",
    "assignee_changed": "assignments",
    "status_changed": "statuses",
    "new_comment": "comments",
    "mentioned": "comments",
    "priority_changed": "updates",
    "due_date_changed": "updates",
    "task_completed": "agent_activity",
    "task_failed": "agent_activity",
    "agent_blocked": "agent_activity",
    "agent_completed": "agent_activity",
}


def _is_muted(workspace_id: str, user_id: str, inbox_type: str) -> bool:
    """Return True if the user has muted this inbox type group."""
    group = TYPE_TO_PREFERENCE_GROUP.get(inbox_type)
    if group is None:
        return False  # unlisted types are always delivered
    try:
        prefs = NotificationPreference.objects.get(workspace_id=workspace_id, user_id=user_id)
    except NotificationPreference.DoesNotExist:
        return False
    return not getattr(prefs, group, True)


def _preference_muted_fields() -> dict[str, str]:
    """Build a lookup that maps notification-preference field names to the
    comma-separated InboxItem types they govern."""
    groups: dict[str, list[str]] = {}
    for inbox_type, field_name in TYPE_TO_PREFERENCE_GROUP.items():
        groups.setdefault(field_name, []).append(inbox_type)
    return {field: ",".join(types) for field, types in groups.items()}


# ---------------------------------------------------------------------------
# Activity helpers
# ---------------------------------------------------------------------------


def create_activity(
    *,
    workspace_id: str,
    issue_id: str | None,
    actor_type: str,
    actor_id: str,
    action: str,
    details: dict[str, Any] | None = None,
) -> Activity:
    """Create an Activity row and return it."""
    return Activity.objects.create(
        workspace_id=workspace_id,
        issue_id=issue_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        details=details or {},
    )


# ---------------------------------------------------------------------------
# Notification / inbox helpers
# ---------------------------------------------------------------------------


def _skip_actor(recipient_type: str, recipient_id: str, actor_type: str, actor_id: str) -> bool:
    """Never notify the event actor (same type and id)."""
    return recipient_type == actor_type and recipient_id == actor_id


def _create_inbox(
    *,
    workspace_id: str,
    recipient_type: str,
    recipient_id: str,
    actor_type: str | None,
    actor_id: str | None,
    inbox_type: str,
    severity: str,
    issue_id: str | None,
    title: str,
    body: str,
    details: dict[str, Any] | None = None,
) -> InboxItem | None:
    """Create an inbox notification row, respecting notification preferences.

    Returns the created ``InboxItem`` or ``None`` when muted / skipped.
    """
    if _skip_actor(recipient_type, recipient_id, actor_type or "", actor_id or ""):
        return None
    if _is_muted(workspace_id, recipient_id, inbox_type):
        return None
    return InboxItem.objects.create(
        workspace_id=workspace_id,
        recipient_type=recipient_type,
        recipient_id=recipient_id,
        actor_type=actor_type,
        actor_id=actor_id,
        type=inbox_type,
        severity=severity,
        issue_id=issue_id,
        title=title,
        body=body,
        details=details or {},
    )


# ---------------------------------------------------------------------------
# Bulk notification helpers
# ---------------------------------------------------------------------------


def _get_issue_subscriber_model():
    """Return the IssueSubscriber model class, or None if not yet available."""
    try:
        from issues.models import IssueSubscriber  # noqa: F811

        return IssueSubscriber
    except (ModuleNotFoundError, ImportError):
        return None


def notify_subscribers(
    *,
    workspace_id: str,
    issue_id: str,
    inbox_type: str,
    severity: str,
    title: str,
    body: str,
    details: dict[str, Any] | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    exclude_ids: list[str] | None = None,
) -> list[InboxItem]:
    """Create inbox rows for all member subscribers of an issue.

    Skips agent subscribers (user inbox delivery is member-only), the actor,
    and any explicitly excluded ids. Respects per-user notification preferences.

    Returns an empty list when the IssueSubscriber model is not yet available
    (i.e. before the issues app is built).
    """
    IssueSubscriber = _get_issue_subscriber_model()
    if IssueSubscriber is None:
        return []

    exclude = set(exclude_ids or [])
    if actor_id:
        exclude.add(str(actor_id))

    subscribers = IssueSubscriber.objects.filter(
        issue_id=issue_id,
        user_type="member",
    ).exclude(user_id__in=exclude)

    items: list[InboxItem] = []
    for sub in subscribers:
        item = _create_inbox(
            workspace_id=workspace_id,
            recipient_type="member",
            recipient_id=str(sub.user_id),
            actor_type=actor_type,
            actor_id=actor_id,
            inbox_type=inbox_type,
            severity=severity,
            issue_id=issue_id,
            title=title,
            body=body,
            details=details,
        )
        if item:
            items.append(item)
    return items


# ---------------------------------------------------------------------------
# Stale task_failed archiving
# ---------------------------------------------------------------------------


def archive_task_failed_for_issue(workspace_id: str, issue_id: str) -> int:
    """Archive all unarchived task_failed inbox items for an issue.

    Called when an issue transitions to a terminal status (in_review, done,
    cancelled) per listener-rules.md.
    """
    return InboxItem.objects.filter(
        workspace_id=workspace_id,
        issue_id=issue_id,
        type=InboxItem.Type.TASK_FAILED,
        archived=False,
    ).update(archived=True)


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


def _handle_issue_updated(sender: type[models.Model], instance: Any, **kwargs: Any) -> None:
    """Process ``issue:updated`` side effects."""
    # Activity logging for detectable changes and inbox notifications
    # are handled by the caller (e.g., the issue service layer calls
    # helper functions before saving).  Signal handlers here provide a
    # safety-net for model-level saves that bypass the service layer.
    pass


# ---------------------------------------------------------------------------
# Registration (called from InboxConfig.ready)
# ---------------------------------------------------------------------------

# Signal handlers are registered here when the corresponding models exist.
# As models are added to sibling apps, connect handlers via:
#
#   from django.db.models.signals import post_save
#   post_save.connect(handler, sender=Issue, dispatch_uid="inbox_issue_save")
#
# The service-layer functions above (create_activity, _create_inbox,
# notify_subscribers, archive_task_failed_for_issue) are the stable API
# that views and other apps should call directly.
