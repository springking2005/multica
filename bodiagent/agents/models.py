"""Agent, Task, Skill, and usage models for the 波笛智能体 platform."""

import uuid

from django.db import models
from django.utils import timezone


class Agent(models.Model):
    """Workspace-scoped AI agent bound directly to a daemon (no runtime layer)."""

    class Provider(models.TextChoices):
        CLAUDE = "claude", "Claude"
        CODEX = "codex", "Codex"
        COPILOT = "copilot", "Copilot"
        OPENCLAW = "openclaw", "OpenClaw"
        OPENCODE = "opencode", "OpenCode"
        HERMES = "hermes", "Hermes"
        GEMINI = "gemini", "Gemini"
        PI = "pi", "Pi"
        CURSOR = "cursor", "Cursor"
        KIMI = "kimi", "Kimi"
        KIRO = "kiro", "Kiro"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    class Visibility(models.TextChoices):
        WORKSPACE = "workspace", "Workspace"
        PRIVATE = "private", "Private"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="agents",
        db_index=True,
    )
    daemon = models.ForeignKey(
        "accounts.Daemon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
        db_index=True,
    )
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=255, default="", blank=True)
    provider = models.CharField(max_length=50, choices=Provider.choices)
    model = models.CharField(max_length=255, default="", blank=True)
    instructions = models.TextField(default="", blank=True)
    max_concurrent_tasks = models.IntegerField(default=3)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.WORKSPACE
    )
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_agents",
    )
    custom_env = models.JSONField(default=dict, blank=True)
    custom_args = models.JSONField(default=dict, blank=True)
    mcp_config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "agent"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace"]),
            models.Index(fields=["daemon"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                name="agent_workspace_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class Task(models.Model):
    """Unit of work dispatched to an agent daemon."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        DISPATCHED = "dispatched", "Dispatched"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name="tasks",
        db_index=True,
    )
    issue = models.ForeignKey(
        "issues.Issue",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tasks",
    )
    daemon = models.ForeignKey(
        "accounts.Daemon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        db_index=True,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED
    )
    priority = models.IntegerField(default=0)
    session_id = models.CharField(max_length=255, default="", blank=True)
    work_dir = models.CharField(max_length=500, default="", blank=True)
    attempt = models.IntegerField(default=1)
    max_attempts = models.IntegerField(default=1)
    parent_task = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sub_tasks",
    )
    failure_reason = models.TextField(default="", blank=True)
    trigger_comment = models.ForeignKey(
        "issues.Comment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_tasks",
    )
    trigger_summary = models.CharField(max_length=255, default="", blank=True)
    autopilot_run_id = models.UUIDField(null=True, blank=True)
    force_fresh_session = models.BooleanField(default=False)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(default=dict, blank=True)
    branch_name = models.CharField(max_length=255, default="", blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_task_queue"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["daemon", "status"]),
            models.Index(fields=["agent", "status"]),
        ]

    def __str__(self) -> str:
        return f"Task {self.id} [{self.status}]"

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class TaskMessage(models.Model):
    """Streamed message from an agent task execution."""

    class Type(models.TextChoices):
        TEXT = "text", "Text"
        TOOL_USE = "tool_use", "Tool Use"
        TOOL_RESULT = "tool_result", "Tool Result"
        ERROR = "error", "Error"
        THINKING = "thinking", "Thinking"
        STATUS = "status", "Status"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    seq = models.IntegerField()
    type = models.CharField(max_length=20, choices=Type.choices)
    tool = models.CharField(max_length=100, default="", blank=True)
    input = models.JSONField(default=dict, blank=True)
    output = models.JSONField(default=dict, blank=True)
    content = models.TextField(default="", blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "task_message"
        ordering = ["task", "seq"]
        indexes = [
            models.Index(fields=["task", "seq"]),
        ]

    def __str__(self) -> str:
        return f"Message {self.seq} for {self.task_id}"


class TaskUsage(models.Model):
    """Token usage and cost for a task per provider/model pair."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="usage_records",
    )
    provider = models.CharField(max_length=50)
    model = models.CharField(max_length=255)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cache_read_tokens = models.IntegerField(default=0)
    cache_write_tokens = models.IntegerField(default=0)
    cost = models.FloatField(default=0.0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "task_usage"
        constraints = [
            models.UniqueConstraint(
                fields=["task", "provider", "model"],
                name="task_usage_task_provider_model_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"Usage for {self.task_id} [{self.provider}/{self.model}]"


class TaskUsageDaily(models.Model):
    """Daily aggregated token usage per workspace/daemon/agent/provider/model."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="daily_usage",
    )
    daemon = models.ForeignKey(
        "accounts.Daemon",
        on_delete=models.CASCADE,
        related_name="daily_usage",
    )
    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name="daily_usage",
    )
    provider = models.CharField(max_length=50)
    model = models.CharField(max_length=255)
    bucket_date = models.DateField()
    total_input_tokens = models.IntegerField(default=0)
    total_output_tokens = models.IntegerField(default=0)
    total_cache_read_tokens = models.IntegerField(default=0)
    total_cache_write_tokens = models.IntegerField(default=0)
    total_cost = models.FloatField(default=0.0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "task_usage_daily"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "daemon", "provider", "model", "bucket_date"],
                name="task_usage_daily_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"Daily usage {self.bucket_date} [{self.provider}/{self.model}]"


class TaskUsageRollupState(models.Model):
    """Singleton row tracking rollup watermark."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    last_processed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "task_usage_rollup_state"

    def __str__(self) -> str:
        return f"Rollup state (last: {self.last_processed_at})"


class TaskUsageDailyDirty(models.Model):
    """Tracks tasks that need re-rollup."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_id = models.UUIDField()

    class Meta:
        db_table = "task_usage_daily_dirty"

    def __str__(self) -> str:
        return f"Dirty marker for task {self.task_id}"


class Skill(models.Model):
    """Reusable skill definition scoped to a workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="skills",
        db_index=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(default="", blank=True)
    content = models.TextField(default="", blank=True)
    config = models.JSONField(default=dict, blank=True)
    created_by_type = models.CharField(max_length=50, default="", blank=True)
    created_by_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "skill"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                name="skill_workspace_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.workspace_id})"

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class SkillFile(models.Model):
    """A file belonging to a skill."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="files",
    )
    path = models.CharField(max_length=500)
    content = models.TextField(default="", blank=True)

    class Meta:
        db_table = "skill_file"
        constraints = [
            models.UniqueConstraint(
                fields=["skill", "path"],
                name="skill_file_skill_path_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.path} @ {self.skill_id}"


class AgentSkill(models.Model):
    """Many-to-many relationship between agents and skills."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name="agent_skills",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="agent_skills",
    )

    class Meta:
        db_table = "agent_skill"
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "skill"],
                name="agent_skill_agent_skill_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"Agent {self.agent_id} <- Skill {self.skill_id}"
