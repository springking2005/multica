"""Admin registrations for issues."""

from django.contrib import admin

from .models import (
    Attachment,
    Comment,
    CommentReaction,
    Issue,
    IssueDependency,
    IssueLabel,
    IssueReaction,
    IssueSubscriber,
    IssueToLabel,
)


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ["title", "workspace_id", "number", "status", "priority", "assignee_type", "created_at"]
    list_filter = ["status", "priority", "assignee_type"]
    search_fields = ["title", "description", "workspace_id"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["issue", "author_type", "type", "resolved_at", "created_at"]
    list_filter = ["type", "author_type"]
    search_fields = ["content"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(IssueSubscriber)
class IssueSubscriberAdmin(admin.ModelAdmin):
    list_display = ["issue", "subscriber_type", "subscriber_id"]
    list_filter = ["subscriber_type"]


@admin.register(IssueDependency)
class IssueDependencyAdmin(admin.ModelAdmin):
    list_display = ["issue", "depends_on", "type"]
    list_filter = ["type"]


@admin.register(IssueLabel)
class IssueLabelAdmin(admin.ModelAdmin):
    list_display = ["name", "workspace_id", "color", "created_at"]
    search_fields = ["name"]


@admin.register(IssueToLabel)
class IssueToLabelAdmin(admin.ModelAdmin):
    list_display = ["issue", "label"]


@admin.register(CommentReaction)
class CommentReactionAdmin(admin.ModelAdmin):
    list_display = ["comment", "actor_type", "emoji", "created_at"]


@admin.register(IssueReaction)
class IssueReactionAdmin(admin.ModelAdmin):
    list_display = ["issue", "actor_type", "emoji", "created_at"]


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["filename", "issue", "comment", "uploader_type", "size_bytes", "created_at"]
    list_filter = ["uploader_type"]
    search_fields = ["filename"]
    readonly_fields = ["id", "created_at"]
