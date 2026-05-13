"""Project models."""

import uuid

from django.db import models


class Project(models.Model):
    """Workspace-scoped project grouping."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class LeadType(models.TextChoices):
        MEMBER = "member", "Member"
        AGENT = "agent", "Agent"

    class Priority(models.TextChoices):
        URGENT = "urgent", "Urgent"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"
        NONE = "none", "None"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="projects",
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=50, default="folder")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    lead_type = models.CharField(
        max_length=20, choices=LeadType.choices, null=True, blank=True
    )
    lead_id = models.UUIDField(null=True, blank=True)
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.NONE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "project"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "status"]),
        ]

    def __str__(self) -> str:
        return self.title


class ProjectResource(models.Model):
    """Typed JSON pointer attached to a project."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="resources"
    )
    workspace_id = models.UUIDField(db_index=True)
    resource_type = models.CharField(max_length=50)
    resource_ref = models.JSONField()
    label = models.TextField(null=True, blank=True)
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "project_resource"
        ordering = ["position", "created_at"]
        indexes = [
            models.Index(fields=["project", "resource_type"]),
            models.Index(fields=["workspace_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "resource_type", "resource_ref"],
                name="project_resource_unique_ref",
            )
        ]

    def __str__(self) -> str:
        return f"{self.resource_type}:{self.resource_ref}"
