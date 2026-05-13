"""Issue, comment, label, reaction, and attachment models."""

import uuid

from django.db import models


class Issue(models.Model):
    """Workspace-scoped issue with MUL-123 style numbering."""

    class Status(models.TextChoices):
        BACKLOG = "backlog", "Backlog"
        TODO = "todo", "Todo"
        IN_PROGRESS = "in_progress", "In progress"
        IN_REVIEW = "in_review", "In review"
        DONE = "done", "Done"
        BLOCKED = "blocked", "Blocked"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.TextChoices):
        URGENT = "urgent", "Urgent"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"
        NONE = "none", "None"

    class AssigneeType(models.TextChoices):
        MEMBER = "member", "Member"
        AGENT = "agent", "Agent"

    class OriginType(models.TextChoices):
        AUTOPILOT = "autopilot", "Autopilot"
        QUICK_CREATE = "quick_create", "Quick create"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="issues",
    )
    number = models.IntegerField(default=0)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.BACKLOG
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.NONE
    )
    assignee_type = models.CharField(
        max_length=20, choices=AssigneeType.choices, null=True, blank=True
    )
    assignee_id = models.UUIDField(null=True, blank=True)
    creator_type = models.CharField(max_length=20, choices=AssigneeType.choices)
    creator_id = models.UUIDField()
    parent_issue = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issues",
    )
    origin_type = models.CharField(
        max_length=20, choices=OriginType.choices, null=True, blank=True
    )
    origin_id = models.UUIDField(null=True, blank=True)
    first_executed_at = models.DateTimeField(null=True, blank=True)
    position = models.FloatField(default=0)
    due_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "issue"
        ordering = ["workspace", "position", "-created_at"]
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["assignee_type", "assignee_id"]),
            models.Index(fields=["parent_issue"]),
            models.Index(fields=["project"]),
            models.Index(fields=["origin_type", "origin_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "number"],
                name="uq_issue_workspace_number",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Comment(models.Model):
    """Comment on an issue with optional resolve state."""

    class AuthorType(models.TextChoices):
        MEMBER = "member", "Member"
        AGENT = "agent", "Agent"

    class Type(models.TextChoices):
        COMMENT = "comment", "Comment"
        STATUS_CHANGE = "status_change", "Status change"
        SYSTEM = "system", "System"
        PROGRESS_UPDATE = "progress_update", "Progress update"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name="comments"
    )
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.CASCADE, related_name="comments"
    )
    author_type = models.CharField(max_length=20, choices=AuthorType.choices)
    author_id = models.UUIDField()
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    content = models.TextField()
    type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.COMMENT
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by_type = models.CharField(
        max_length=20, choices=AuthorType.choices, null=True, blank=True
    )
    resolved_by_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "comment"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["issue", "created_at"]),
            models.Index(fields=["issue", "resolved_at"]),
        ]

    def __str__(self) -> str:
        return f"Comment {self.id} on {self.issue_id}"


class IssueSubscriber(models.Model):
    """Subscription to issue updates."""

    class SubscriberType(models.TextChoices):
        MEMBER = "member", "Member"
        AGENT = "agent", "Agent"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name="subscribers"
    )
    subscriber_type = models.CharField(max_length=20, choices=SubscriberType.choices)
    subscriber_id = models.UUIDField()

    class Meta:
        db_table = "issue_subscriber"
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "subscriber_type", "subscriber_id"],
                name="uq_issue_subscriber",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.subscriber_type}:{self.subscriber_id} -> {self.issue_id}"


class IssueDependency(models.Model):
    """Directed dependency edge between issues."""

    class Type(models.TextChoices):
        BLOCKS = "blocks", "Blocks"
        BLOCKED_BY = "blocked_by", "Blocked by"
        RELATED = "related", "Related"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name="dependencies"
    )
    depends_on = models.ForeignKey(
        Issue,
        on_delete=models.CASCADE,
        related_name="dependents",
    )
    type = models.CharField(max_length=20, choices=Type.choices)

    class Meta:
        db_table = "issue_dependency"

    def __str__(self) -> str:
        return f"{self.issue_id} {self.type} {self.depends_on_id}"


class IssueLabel(models.Model):
    """Per-workspace label with color."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="issue_labels",
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default="#6B7280")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "issue_label"
        constraints = [
            models.UniqueConstraint(
                models.functions.Lower("name"),
                "workspace",
                name="issue_label_workspace_name_lower_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class IssueToLabel(models.Model):
    """M2M through table linking issues to labels."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE)
    label = models.ForeignKey(IssueLabel, on_delete=models.CASCADE)

    class Meta:
        db_table = "issue_to_label"
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "label"],
                name="issue_to_label_pkey",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.issue_id} <- {self.label_id}"


class CommentReaction(models.Model):
    """Emoji reaction on a comment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comment = models.ForeignKey(
        Comment, on_delete=models.CASCADE, related_name="reactions"
    )
    actor_type = models.CharField(
        max_length=20, choices=Comment.AuthorType.choices
    )
    actor_id = models.UUIDField()
    emoji = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comment_reaction"
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "actor_type", "actor_id", "emoji"],
                name="uq_comment_reaction",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.emoji} by {self.actor_type}:{self.actor_id} on comment {self.comment_id}"


class IssueReaction(models.Model):
    """Emoji reaction on an issue."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name="reactions"
    )
    actor_type = models.CharField(
        max_length=20, choices=Comment.AuthorType.choices
    )
    actor_id = models.UUIDField()
    emoji = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "issue_reaction"
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "actor_type", "actor_id", "emoji"],
                name="uq_issue_reaction",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.emoji} by {self.actor_type}:{self.actor_id} on issue {self.issue_id}"


class Attachment(models.Model):
    """File attachment for an issue or comment."""

    class UploaderType(models.TextChoices):
        MEMBER = "member", "Member"
        AGENT = "agent", "Agent"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey(
        Issue,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
    )
    uploader_type = models.CharField(max_length=20, choices=UploaderType.choices)
    uploader_id = models.UUIDField()
    url = models.TextField()
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attachment"
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(issue__isnull=False) | models.Q(comment__isnull=False),
                name="attachment_target_check",
            ),
        ]

    def __str__(self) -> str:
        return self.filename
