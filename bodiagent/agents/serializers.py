"""DRF serializers for agent, task, skill, and usage APIs."""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    Agent,
    AgentSkill,
    Skill,
    SkillFile,
    Task,
    TaskMessage,
    TaskUsage,
    TaskUsageDaily,
)


class AgentSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(source="workspace.id", read_only=True)
    daemon_id = serializers.UUIDField(required=True)
    owner_id = serializers.UUIDField(source="owner.id", read_only=True)

    class Meta:
        model = Agent
        fields = [
            "id",
            "workspace_id",
            "daemon_id",
            "name",
            "description",
            "provider",
            "model",
            "instructions",
            "max_concurrent_tasks",
            "status",
            "visibility",
            "owner_id",
            "custom_env",
            "custom_args",
            "mcp_config",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "workspace_id", "owner_id", "created_at", "updated_at"]


class AgentCreateSerializer(AgentSerializer):
    daemon = serializers.HiddenField(default=None)
    skill_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, write_only=True
    )

    class Meta(AgentSerializer.Meta):
        fields = AgentSerializer.Meta.fields + ["daemon", "skill_ids"]

    def create(self, validated_data):
        skill_ids = validated_data.pop("skill_ids", [])
        agent = Agent.objects.create(**validated_data)
        for skill_id in skill_ids:
            AgentSkill.objects.get_or_create(agent=agent, skill_id=skill_id)
        return agent


class AgentUpdateSerializer(AgentSerializer):
    daemon_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta(AgentSerializer.Meta):
        read_only_fields = [
            "id",
            "workspace_id",
            "owner_id",
            "created_at",
            "updated_at",
        ]


class AgentArchiveSerializer(serializers.Serializer):
    """No fields needed — POST triggers the archive/restore action."""


class SetAgentSkillsSerializer(serializers.Serializer):
    skill_ids = serializers.ListField(child=serializers.UUIDField())


class TaskSerializer(serializers.ModelSerializer):
    agent_id = serializers.UUIDField(source="agent.id", read_only=True)
    issue_id = serializers.UUIDField(read_only=True)
    daemon_id = serializers.UUIDField(read_only=True)
    parent_task_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "agent_id",
            "issue_id",
            "daemon_id",
            "status",
            "priority",
            "session_id",
            "work_dir",
            "attempt",
            "max_attempts",
            "parent_task_id",
            "failure_reason",
            "trigger_comment_id",
            "trigger_summary",
            "autopilot_run_id",
            "force_fresh_session",
            "last_heartbeat_at",
            "result",
            "branch_name",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "agent_id",
            "issue_id",
            "daemon_id",
            "status",
            "session_id",
            "attempt",
            "parent_task_id",
            "failure_reason",
            "trigger_comment_id",
            "autopilot_run_id",
            "last_heartbeat_at",
            "result",
            "branch_name",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]


class DaemonTaskClaimSerializer(TaskSerializer):
    agent_name = serializers.CharField(source="agent.name", read_only=True)
    provider = serializers.CharField(source="agent.provider", read_only=True)
    model = serializers.CharField(source="agent.model", read_only=True)
    system_prompt = serializers.CharField(source="agent.instructions", read_only=True)
    custom_args = serializers.JSONField(source="agent.custom_args", read_only=True)
    mcp_config = serializers.JSONField(source="agent.mcp_config", read_only=True)
    prompt = serializers.SerializerMethodField()
    context = serializers.SerializerMethodField()

    class Meta(TaskSerializer.Meta):
        fields = TaskSerializer.Meta.fields + [
            "agent_name",
            "provider",
            "model",
            "system_prompt",
            "custom_args",
            "mcp_config",
            "prompt",
            "context",
        ]

    def get_prompt(self, obj: Task) -> str:
        if obj.trigger_summary:
            return obj.trigger_summary
        if obj.issue_id and obj.issue:
            parts = [obj.issue.title]
            if obj.issue.description:
                parts.append(obj.issue.description)
            return "\n\n".join(parts)
        return ""

    def get_context(self, obj: Task) -> dict:
        return {
            "workspace_id": str(obj.agent.workspace_id),
            "issue_id": str(obj.issue_id) if obj.issue_id else None,
            "autopilot_run_id": str(obj.autopilot_run_id) if obj.autopilot_run_id else None,
        }


class TaskQueueSerializer(serializers.Serializer):
    agent_id = serializers.UUIDField(required=True)
    issue_id = serializers.UUIDField(required=False, allow_null=True)
    priority = serializers.IntegerField(required=False, default=0)
    trigger_summary = serializers.CharField(required=False, allow_blank=True, default="")
    trigger_comment_id = serializers.UUIDField(required=False, allow_null=True)
    autopilot_run_id = serializers.UUIDField(required=False, allow_null=True)
    parent_task_id = serializers.UUIDField(required=False, allow_null=True)
    force_fresh_session = serializers.BooleanField(required=False, default=False)
    max_attempts = serializers.IntegerField(required=False, default=1)


class TaskClaimSerializer(serializers.Serializer):
    daemon_id = serializers.UUIDField(required=True)
    session_id = serializers.CharField(required=False, allow_blank=True, default="")
    work_dir = serializers.CharField(required=False, allow_blank=True, default="")


class TaskProgressSerializer(serializers.Serializer):
    seq = serializers.IntegerField(required=False, default=0)
    type = serializers.CharField(required=False, allow_blank=True, default="status")
    content = serializers.CharField(required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)


class TaskCompleteSerializer(serializers.Serializer):
    result = serializers.JSONField(required=False, default=dict)
    branch_name = serializers.CharField(required=False, allow_blank=True, default="")


class TaskFailSerializer(serializers.Serializer):
    failure_reason = serializers.CharField(required=False, allow_blank=True, default="")


class TaskCancelSerializer(serializers.Serializer):
    """No fields needed — POST triggers cancel."""


class TaskMessageSerializer(serializers.ModelSerializer):
    task_id = serializers.UUIDField(source="task.id", read_only=True)

    class Meta:
        model = TaskMessage
        fields = [
            "id",
            "task_id",
            "seq",
            "type",
            "tool",
            "input",
            "output",
            "content",
            "metadata",
            "created_at",
        ]
        read_only_fields = ["id", "task_id", "created_at"]


class TaskMessageBatchSerializer(serializers.Serializer):
    messages = serializers.ListField(child=serializers.JSONField())


class TaskUsageSerializer(serializers.ModelSerializer):
    task_id = serializers.UUIDField(source="task.id", read_only=True)

    class Meta:
        model = TaskUsage
        fields = [
            "id",
            "task_id",
            "provider",
            "model",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "cost",
            "created_at",
        ]
        read_only_fields = ["id", "task_id", "created_at"]


class TaskUsageDailySerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(source="workspace.id", read_only=True)
    daemon_id = serializers.UUIDField(source="daemon.id", read_only=True)
    agent_id = serializers.UUIDField(source="agent.id", read_only=True)

    class Meta:
        model = TaskUsageDaily
        fields = [
            "id",
            "workspace_id",
            "daemon_id",
            "agent_id",
            "provider",
            "model",
            "bucket_date",
            "total_input_tokens",
            "total_output_tokens",
            "total_cache_read_tokens",
            "total_cache_write_tokens",
            "total_cost",
            "created_at",
        ]
        read_only_fields = ["id"]


class SkillSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(source="workspace.id", read_only=True)

    class Meta:
        model = Skill
        fields = [
            "id",
            "workspace_id",
            "name",
            "description",
            "content",
            "config",
            "created_by_type",
            "created_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "workspace_id", "created_at", "updated_at"]


class SkillFileSerializer(serializers.ModelSerializer):
    skill_id = serializers.UUIDField(source="skill.id", read_only=True)

    class Meta:
        model = SkillFile
        fields = [
            "id",
            "skill_id",
            "path",
            "content",
        ]
        read_only_fields = ["id", "skill_id"]


class SkillFileBatchSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField())
    )


class SkillImportSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    content = serializers.CharField(required=False, allow_blank=True, default="")
    config = serializers.JSONField(required=False, default=dict)
    files = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        required=False,
        default=list,
    )
