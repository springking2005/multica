"""Admin registrations for agents."""

from django.contrib import admin

from .models import (
    Agent,
    AgentSkill,
    Skill,
    SkillFile,
    Task,
    TaskMessage,
    TaskUsage,
    TaskUsageDaily,
    TaskUsageDailyDirty,
    TaskUsageRollupState,
)


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ["name", "workspace_id", "daemon_id", "provider", "model", "status", "visibility", "created_at"]
    list_filter = ["provider", "status", "visibility"]
    search_fields = ["name", "description", "workspace_id"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["id", "agent_id", "daemon_id", "status", "priority", "attempt", "created_at"]
    list_filter = ["status", "priority"]
    search_fields = ["agent__name", "session_id", "trigger_summary"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(TaskMessage)
class TaskMessageAdmin(admin.ModelAdmin):
    list_display = ["task_id", "seq", "type", "tool", "created_at"]
    list_filter = ["type"]
    search_fields = ["content", "tool"]
    readonly_fields = ["id", "created_at"]


@admin.register(TaskUsage)
class TaskUsageAdmin(admin.ModelAdmin):
    list_display = ["task_id", "provider", "model", "input_tokens", "output_tokens", "cost", "created_at"]
    list_filter = ["provider", "model"]
    search_fields = ["task_id", "provider", "model"]
    readonly_fields = ["id", "created_at"]


@admin.register(TaskUsageDaily)
class TaskUsageDailyAdmin(admin.ModelAdmin):
    list_display = ["workspace_id", "daemon_id", "agent_id", "provider", "model", "bucket_date", "total_cost"]
    list_filter = ["provider", "model"]
    search_fields = ["workspace_id", "daemon_id"]
    readonly_fields = ["id", "created_at"]


@admin.register(TaskUsageRollupState)
class TaskUsageRollupStateAdmin(admin.ModelAdmin):
    list_display = ["id", "last_processed_at"]
    readonly_fields = ["id"]


@admin.register(TaskUsageDailyDirty)
class TaskUsageDailyDirtyAdmin(admin.ModelAdmin):
    list_display = ["id", "task_id"]
    search_fields = ["task_id"]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ["name", "workspace_id", "created_by_type", "created_at"]
    search_fields = ["name", "description"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(SkillFile)
class SkillFileAdmin(admin.ModelAdmin):
    list_display = ["skill_id", "path"]
    search_fields = ["path", "skill__name"]


@admin.register(AgentSkill)
class AgentSkillAdmin(admin.ModelAdmin):
    list_display = ["agent_id", "skill_id"]
    search_fields = ["agent__name", "skill__name"]
