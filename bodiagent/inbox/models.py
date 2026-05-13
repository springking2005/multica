"""Inbox item, activity log, and pinned item models."""

import uuid

from django.db import models


class InboxItem(models.Model):
    """Notification / inbox item for a member or agent recipient.

    Maps to the ``inbox_item`` table in the schema contract.
    """

    class RecipientType(models.TextChoices):
        MEMBER = "member", "Member"
        AGENT = "agent", "Agent"

    class ActorType(models.TextChoices):
        MEMBER = "member", "Member"
        AGENT = "agent", "Agent"
        SYSTEM = "system", "System"

    class Type(models.TextChoices):
        ISSUE_ASSIGNED = "issue_assigned", "Issue Assigned"
        UNASSIGNED = "unassigned", "Unassigned"
        ASSIGNEE_CHANGED = "assignee_changed", "Assignee Changed"
        STATUS_CHANGED = "status_changed", "Status Changed"
        PRIORITY_CHANGED = "priority_changed", "Priority Changed"
        DUE_DATE_CHANGED = "due_date_changed", "Due Date Changed"
        NEW_COMMENT = "new_comment", "New Comment"
        MENTIONED = "mentioned", "Mentioned"
        REVIEW_REQUESTED = "review_requested", "Review Requested"
        TASK_COMPLETED = "task_completed", "Task Completed"
        TASK_FAILED = "task_failed", "Task Failed"
        AGENT_BLOCKED = "agent_blocked", "Agent Blocked"
        AGENT_COMPLETED = "agent_completed", "Agent Completed"
        REACTION_ADDED = "reaction_added", "Reaction Added"
        QUICK_CREATE_DONE = "quick_create_done", "Quick Create Done"
        QUICK_CREATE_FAILED = "quick_create_failed", "Quick Create Failed"

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="inbox_items",
        db_index=True,
    )
    recipient_type = models.CharField(max_length=20, choices=RecipientType.choices)
    recipient_id = models.UUIDField()
    actor_type = models.CharField(max_length=20, choices=ActorType.choices, null=True, blank=True)
    actor_id = models.UUIDField(null=True, blank=True)
    type = models.CharField(max_length=30, choices=Type.choices)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO)
    # TODO: change to FK("issues.Issue", on_delete=models.CASCADE, null=True, blank=True)
    # once the Issue model is added to the issues app.
    issue_id = models.UUIDField(null=True, blank=True, db_index=True)
    title = models.CharField(max_length=500)
    body = models.TextField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)
    read = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inbox_item"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_type", "recipient_id", "read"], name="idx_inbox_recipient"),
            models.Index(fields=["workspace", "created_at"], name="idx_inbox_ws_created"),
        ]

    def __str__(self) -> str:
        return f"[{self.type}] {self.title}"


class Activity(models.Model):
    """Issue / workspace activity log entry.

    Maps to the ``activity_log`` table in the schema contract.
    """

    class ActorType(models.TextChoices):
        MEMBER = "member", "Member"
        AGENT = "agent", "Agent"
        SYSTEM = "system", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="activities",
        db_index=True,
    )
    # TODO: change to FK("issues.Issue", on_delete=models.CASCADE, null=True, blank=True)
    # once the Issue model is added to the issues app.
    issue_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_type = models.CharField(max_length=20, choices=ActorType.choices)
    actor_id = models.UUIDField()
    action = models.CharField(max_length=100)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "activity_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "created_at"], name="idx_activity_ws_created"),
            models.Index(fields=["issue_id", "created_at"], name="idx_activity_issue_created"),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_type}:{self.actor_id}"


class Pin(models.Model):
    """User-pinned item (issue or project) within a workspace."""

    class ItemType(models.TextChoices):
        ISSUE = "issue", "Issue"
        PROJECT = "project", "Project"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="pins",
        db_index=True,
    )
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    item_id = models.UUIDField()
    pinned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="pins",
    )
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pinned_item"
        ordering = ["position", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "item_type", "item_id", "pinned_by"],
                name="pin_workspace_item_user_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_type}:{self.item_id} pinned by {self.pinned_by_id}"
