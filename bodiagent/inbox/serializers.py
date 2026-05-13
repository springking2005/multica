"""DRF serializers for inbox, activity, and pin APIs."""

from rest_framework import serializers

from .models import Activity, InboxItem, Pin


class InboxItemSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = InboxItem
        fields = [
            "id",
            "workspace_id",
            "recipient_type",
            "recipient_id",
            "actor_type",
            "actor_id",
            "type",
            "severity",
            "issue_id",
            "title",
            "body",
            "details",
            "read",
            "archived",
            "created_at",
        ]
        read_only_fields = ["id", "workspace_id", "created_at"]


class InboxItemReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = InboxItem
        fields = ["read"]


class InboxItemArchiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = InboxItem
        fields = ["archived"]


class ActivitySerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Activity
        fields = [
            "id",
            "workspace_id",
            "issue_id",
            "actor_type",
            "actor_id",
            "action",
            "details",
            "created_at",
        ]
        read_only_fields = ["id", "workspace_id", "created_at"]


class PinSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Pin
        fields = [
            "id",
            "workspace_id",
            "item_type",
            "item_id",
            "position",
            "pinned_by",
            "created_at",
        ]
        read_only_fields = ["id", "workspace_id", "pinned_by", "position", "created_at"]


class CreatePinSerializer(serializers.Serializer):
    item_type = serializers.ChoiceField(choices=Pin.ItemType.choices)
    item_id = serializers.UUIDField()


class ReorderPinsSerializer(serializers.Serializer):
    item_ids = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
    )
