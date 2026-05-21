"""DRF serializers for chat sessions and messages."""

from rest_framework import serializers

from accounts.workspace_scope import resolve_workspace_id, resolve_workspace_member, validate_issue_id

from .models import ChatMessage, ChatSession


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = (
            "id",
            "workspace",
            "agent",
            "creator_type",
            "creator_id",
            "issue",
            "title",
            "session_id",
            "work_dir",
            "daemon",
            "status",
            "context",
            "unread_since",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "creator_type",
            "creator_id",
            "session_id",
            "work_dir",
            "daemon",
            "status",
            "unread_since",
            "created_at",
            "updated_at",
        )


class CreateChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = (
            "agent",
            "title",
            "issue",
            "context",
        )

    def validate(self, attrs):
        request = self.context.get("request")
        workspace_id = resolve_workspace_id(request)
        agent = attrs.get("agent")
        if agent and agent.workspace_id != workspace_id:
            raise serializers.ValidationError({"agent": "Agent must belong to the workspace."})
        issue = attrs.get("issue")
        if issue:
            validate_issue_id(issue.id, workspace_id, field_name="issue")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        workspace_id = resolve_workspace_id(request)
        member = resolve_workspace_member(request, workspace_id)
        validated_data["workspace_id"] = workspace_id
        validated_data["creator_type"] = ChatSession.CREATOR_MEMBER
        validated_data["creator_id"] = member.id
        return super().create(validated_data)


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = (
            "id",
            "session",
            "task",
            "role",
            "content",
            "failure_reason",
            "elapsed_ms",
            "metadata",
            "created_at",
        )
        read_only_fields = (
            "id",
            "task",
            "role",
            "failure_reason",
            "elapsed_ms",
            "metadata",
            "created_at",
        )


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField()

    def create(self, validated_data):
        session = self.context["session"]
        return ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content=validated_data["content"],
        )
