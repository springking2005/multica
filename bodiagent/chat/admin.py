"""Django admin registrations for chat."""

from django.contrib import admin

from .models import ChatMessage, ChatSession


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "workspace", "agent", "status", "creator_type", "created_at")
    list_filter = ("status", "creator_type")
    search_fields = ("title", "session_id")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "content_preview", "created_at")
    list_filter = ("role",)
    readonly_fields = ("id", "created_at")

    @admin.display(description="Content")
    def content_preview(self, obj):
        return obj.content[:120]
