"""Chat session and message models for 波笛智能体."""

import uuid

from django.db import models
from django.utils import timezone


class ChatSession(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_ARCHIVED, "Archived"),
    )

    CREATOR_MEMBER = "member"
    CREATOR_AGENT = "agent"
    CREATOR_CHOICES = (
        (CREATOR_MEMBER, "Member"),
        (CREATOR_AGENT, "Agent"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace", on_delete=models.CASCADE, related_name="chat_sessions"
    )
    agent = models.ForeignKey(
        "agents.Agent", on_delete=models.CASCADE, related_name="chat_sessions"
    )
    creator_type = models.CharField(max_length=16, choices=CREATOR_CHOICES)
    creator_id = models.UUIDField()
    issue = models.ForeignKey(
        "issues.Issue", on_delete=models.SET_NULL, blank=True, null=True, related_name="chat_sessions"
    )
    title = models.CharField(max_length=500, default="", blank=True)
    session_id = models.CharField(max_length=255, default="", blank=True)
    work_dir = models.CharField(max_length=500, default="", blank=True)
    daemon = models.ForeignKey(
        "accounts.Daemon", on_delete=models.SET_NULL, blank=True, null=True, related_name="chat_sessions"
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    context = models.JSONField(default=dict, blank=True)
    unread_since = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "chat_session"
        indexes = [
            models.Index(fields=["workspace"], name="idx_chat_session_workspace"),
            models.Index(fields=["creator_id", "workspace"], name="idx_chat_session_creator"),
        ]

    def __str__(self) -> str:
        return self.title or str(self.id)

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class ChatMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = (
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="messages"
    )
    task = models.ForeignKey(
        "agents.Task", on_delete=models.SET_NULL, blank=True, null=True, related_name="chat_messages"
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    failure_reason = models.CharField(max_length=255, blank=True, null=True)
    elapsed_ms = models.IntegerField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "chat_message"
        indexes = [
            models.Index(fields=["session", "created_at"], name="idx_chat_message_session"),
        ]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:80]}"
