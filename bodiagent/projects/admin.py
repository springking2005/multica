"""Admin registrations for projects."""

from django.contrib import admin

from .models import Project, ProjectResource


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["title", "workspace_id", "status", "priority", "lead_type", "created_at"]
    list_filter = ["status", "priority", "lead_type"]
    search_fields = ["title", "description", "workspace_id"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(ProjectResource)
class ProjectResourceAdmin(admin.ModelAdmin):
    list_display = ["project", "resource_type", "created_at"]
    list_filter = ["resource_type"]
    search_fields = ["project__title", "resource_type"]
    readonly_fields = ["id", "created_at"]
