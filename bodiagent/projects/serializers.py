"""Serializers for project APIs."""

from __future__ import annotations

from uuid import UUID

from rest_framework import serializers

from .models import Project, ProjectResource


class ProjectSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "workspace_id",
            "title",
            "description",
            "icon",
            "status",
            "lead_type",
            "lead_id",
            "priority",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "workspace_id", "status", "created_at", "updated_at"]

    def validate(self, attrs: dict) -> dict:
        lead_type = attrs.get("lead_type", getattr(self.instance, "lead_type", None))
        lead_id = attrs.get("lead_id", getattr(self.instance, "lead_id", None))
        if lead_type and not lead_id:
            raise serializers.ValidationError(
                {"lead_id": "lead_id is required when lead_type is set."}
            )
        if lead_id and not lead_type:
            raise serializers.ValidationError(
                {"lead_type": "lead_type is required when lead_id is set."}
            )
        return attrs


class ProjectUpdateSerializer(ProjectSerializer):
    class Meta(ProjectSerializer.Meta):
        read_only_fields = ["id", "workspace_id", "created_at", "updated_at"]


class ProjectResourceSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(source="project.id", read_only=True)
    resource_id = serializers.SerializerMethodField()

    class Meta:
        model = ProjectResource
        fields = [
            "id",
            "project_id",
            "resource_type",
            "resource_id",
            "resource_ref",
            "created_at",
        ]
        read_only_fields = ["id", "project_id", "resource_id", "created_at"]

    def get_resource_id(self, obj: ProjectResource) -> str | None:
        resource_ref = obj.resource_ref
        if isinstance(resource_ref, dict):
            value = resource_ref.get("id") or resource_ref.get("resource_id")
            return str(value) if value else None
        return None


class ProjectResourceCreateSerializer(serializers.ModelSerializer):
    resource_id = serializers.UUIDField(required=True, write_only=True)

    class Meta:
        model = ProjectResource
        fields = ["resource_type", "resource_id", "resource_ref"]
        extra_kwargs = {
            "resource_ref": {"required": False},
        }

    def validate(self, attrs: dict) -> dict:
        resource_id: UUID = attrs.pop("resource_id")
        attrs.setdefault("resource_ref", {"id": str(resource_id)})
        return attrs

    def to_representation(self, instance: ProjectResource) -> dict:
        return ProjectResourceSerializer(instance, context=self.context).data
