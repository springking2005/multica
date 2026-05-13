"""Admin registrations for autopilots."""

from django.contrib import admin

from .models import Autopilot, AutopilotRun, AutopilotTrigger


@admin.register(Autopilot)
class AutopilotAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "workspace_id",
        "assignee",
        "status",
        "execution_mode",
        "last_run_at",
        "created_at",
    ]
    list_filter = ["status", "execution_mode"]
    search_fields = ["title", "description", "workspace_id"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(AutopilotTrigger)
class AutopilotTriggerAdmin(admin.ModelAdmin):
    list_display = [
        "autopilot",
        "kind",
        "enabled",
        "label",
        "next_run_at",
        "last_fired_at",
        "created_at",
    ]
    list_filter = ["kind", "enabled"]
    search_fields = ["label", "autopilot__title"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(AutopilotRun)
class AutopilotRunAdmin(admin.ModelAdmin):
    list_display = [
        "autopilot",
        "source",
        "status",
        "triggered_at",
        "completed_at",
        "created_at",
    ]
    list_filter = ["source", "status"]
    search_fields = ["autopilot__title", "issue_id", "task_id"]
    readonly_fields = ["id", "triggered_at", "created_at"]
