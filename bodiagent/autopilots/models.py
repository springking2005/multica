"""Autopilot and autopilot run models for 波笛智能体."""

import uuid

from django.db import models
from django.utils import timezone as tz


class Autopilot(models.Model):
    """Scheduled or webhook-triggered automation."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"

    class ExecutionMode(models.TextChoices):
        CREATE_ISSUE = "create_issue", "Create Issue"
        RUN_ONLY = "run_only", "Run Only"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.CASCADE, related_name="autopilots"
    )
    title = models.CharField(max_length=500)
    description = models.TextField(default="", blank=True)
    assignee = models.ForeignKey(
        "agents.Agent", on_delete=models.CASCADE, related_name="autopilots"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    execution_mode = models.CharField(
        max_length=20,
        choices=ExecutionMode.choices,
        default=ExecutionMode.CREATE_ISSUE,
    )
    issue_title_template = models.CharField(max_length=500, default="", blank=True)
    created_by_type = models.CharField(
        max_length=16, choices=(("member", "Member"), ("agent", "Agent"))
    )
    created_by_id = models.UUIDField()
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=tz.now)
    updated_at = models.DateTimeField(default=tz.now)

    class Meta:
        db_table = "autopilot"
        indexes = [
            models.Index(fields=["workspace", "status"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        self.updated_at = tz.now()
        super().save(*args, **kwargs)


class AutopilotTrigger(models.Model):
    """Trigger configuration for an autopilot."""

    class Kind(models.TextChoices):
        SCHEDULE = "schedule", "Schedule"
        WEBHOOK = "webhook", "Webhook"
        API = "api", "API"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    autopilot = models.ForeignKey(
        Autopilot, on_delete=models.CASCADE, related_name="triggers"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    enabled = models.BooleanField(default=True)
    cron_expression = models.CharField(max_length=100, default="", blank=True)
    timezone = models.CharField(max_length=50, default="Asia/Shanghai")
    next_run_at = models.DateTimeField(null=True, blank=True)
    webhook_token = models.CharField(max_length=255, null=True, blank=True)
    label = models.CharField(max_length=255, default="", blank=True)
    last_fired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=tz.now)
    updated_at = models.DateTimeField(default=tz.now)

    class Meta:
        db_table = "autopilot_trigger"

    def __str__(self) -> str:
        return f"{self.autopilot.title} [{self.kind}]"

    def save(self, *args, **kwargs):
        self.updated_at = tz.now()
        super().save(*args, **kwargs)


class AutopilotRun(models.Model):
    """Execution record of an autopilot trigger."""

    class Source(models.TextChoices):
        SCHEDULE = "schedule", "Schedule"
        WEBHOOK = "webhook", "Webhook"
        API = "api", "API"
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        ISSUE_CREATED = "issue_created", "Issue Created"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    autopilot = models.ForeignKey(
        Autopilot, on_delete=models.CASCADE, related_name="runs"
    )
    trigger = models.ForeignKey(
        AutopilotTrigger,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    source = models.CharField(max_length=20, choices=Source.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ISSUE_CREATED,
    )
    issue = models.ForeignKey(
        "issues.Issue",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="autopilot_runs",
    )
    task = models.ForeignKey(
        "agents.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="autopilot_runs",
    )
    triggered_at = models.DateTimeField(default=tz.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(default="", blank=True)
    trigger_payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=tz.now)

    class Meta:
        db_table = "autopilot_run"

    def __str__(self) -> str:
        return f"Run {self.id} ({self.status})"
