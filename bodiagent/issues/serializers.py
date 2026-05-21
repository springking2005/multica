"""Serializers for issue APIs."""

from __future__ import annotations

from rest_framework import serializers

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


class IssueLabelSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(source="workspace.id", read_only=True)

    class Meta:
        model = IssueLabel
        fields = [
            "id",
            "workspace_id",
            "name",
            "color",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "workspace_id", "created_at", "updated_at"]


class IssueSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueSubscriber
        fields = [
            "id",
            "issue",
            "subscriber_type",
            "subscriber_id",
        ]
        read_only_fields = ["id", "issue"]


class IssueDependencySerializer(serializers.ModelSerializer):
    depends_on_title = serializers.CharField(source="depends_on.title", read_only=True)
    depends_on_number = serializers.IntegerField(source="depends_on.number", read_only=True)

    class Meta:
        model = IssueDependency
        fields = [
            "id",
            "issue",
            "depends_on",
            "depends_on_title",
            "depends_on_number",
            "type",
        ]
        read_only_fields = ["id", "issue", "depends_on_title", "depends_on_number"]


class IssueToLabelSerializer(serializers.ModelSerializer):
    label = IssueLabelSerializer(read_only=True)
    label_id = serializers.PrimaryKeyRelatedField(
        source="label",
        queryset=IssueLabel.objects.all(),
        write_only=True,
    )

    class Meta:
        model = IssueToLabel
        fields = ["issue", "label", "label_id"]


class IssueSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(read_only=True)
    labels = IssueToLabelSerializer(source="issuetolabel_set", many=True, read_only=True)

    class Meta:
        model = Issue
        fields = [
            "id",
            "workspace_id",
            "number",
            "title",
            "description",
            "status",
            "priority",
            "assignee_type",
            "assignee_id",
            "creator_type",
            "creator_id",
            "parent_issue",
            "project",
            "origin_type",
            "origin_id",
            "first_executed_at",
            "position",
            "due_date",
            "labels",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "workspace_id",
            "number",
            "created_at",
            "updated_at",
        ]


class IssueCreateSerializer(IssueSerializer):
    class Meta(IssueSerializer.Meta):
        read_only_fields = [
            "id",
            "workspace_id",
            "number",
            "creator_type",
            "creator_id",
            "labels",
            "first_executed_at",
            "created_at",
            "updated_at",
        ]


class IssueBatchUpdateSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)
    status = serializers.ChoiceField(choices=Issue.Status.choices, required=False)
    priority = serializers.ChoiceField(choices=Issue.Priority.choices, required=False)
    assignee_type = serializers.ChoiceField(
        choices=Issue.AssigneeType.choices, required=False, allow_null=True
    )
    assignee_id = serializers.UUIDField(required=False, allow_null=True)
    project_id = serializers.UUIDField(required=False, allow_null=True)
    due_date = serializers.DateTimeField(required=False, allow_null=True)


class IssueReorderSerializer(serializers.Serializer):
    issue_id = serializers.UUIDField()
    position = serializers.FloatField()


class IssueChildrenSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)


class CommentSerializer(serializers.ModelSerializer):
    issue_id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id",
            "issue_id",
            "workspace_id",
            "author_type",
            "author_id",
            "parent",
            "content",
            "type",
            "resolved_at",
            "resolved_by_type",
            "resolved_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "issue_id",
            "workspace_id",
            "author_type",
            "author_id",
            "resolved_at",
            "resolved_by_type",
            "resolved_by_id",
            "created_at",
            "updated_at",
        ]


class CommentResolveSerializer(serializers.Serializer):
    resolved_at = serializers.DateTimeField(required=False)


class CommentReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommentReaction
        fields = [
            "id",
            "comment",
            "actor_type",
            "actor_id",
            "emoji",
            "created_at",
        ]
        read_only_fields = ["id", "comment", "created_at"]


class IssueReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueReaction
        fields = [
            "id",
            "issue",
            "actor_type",
            "actor_id",
            "emoji",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = [
            "id",
            "issue",
            "comment",
            "uploader_type",
            "uploader_id",
            "url",
            "filename",
            "content_type",
            "size_bytes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
