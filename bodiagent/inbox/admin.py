"""Admin registrations for inbox, activity, and pin models."""

from django.contrib import admin

from .models import Activity, InboxItem, Pin


@admin.register(InboxItem)
class InboxItemAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "type",
        "severity",
        "recipient_type",
        "recipient_id",
        "workspace_id",
        "read",
        "archived",
        "created_at",
    ]
    list_filter = ["type", "severity", "recipient_type", "read", "archived"]
    search_fields = ["title", "body", "recipient_id", "actor_id"]
    readonly_fields = ["id", "created_at"]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ["action", "actor_type", "actor_id", "workspace_id", "issue_id", "created_at"]
    list_filter = ["action", "actor_type"]
    search_fields = ["action", "actor_id", "issue_id"]
    readonly_fields = ["id", "created_at"]


@admin.register(Pin)
class PinAdmin(admin.ModelAdmin):
    list_display = ["item_type", "item_id", "pinned_by", "workspace_id", "position", "created_at"]
    list_filter = ["item_type"]
    search_fields = ["item_id", "pinned_by__email"]
    readonly_fields = ["id", "created_at"]
