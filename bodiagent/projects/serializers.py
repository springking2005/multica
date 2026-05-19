"""Serializers for project APIs."""

from __future__ import annotations

from uuid import UUID

from rest_framework import serializers

from .models import Project, ProjectResource


class ProjectSerializer(serializers.ModelSerializer):
    workspace_id = serializers.UUIDField(read_only=True)
    issue_count = serializers.SerializerMethodField()
    done_issue_count = serializers.SerializerMethodField()
    resource_count = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    progress_label = serializers.SerializerMethodField()
    lead_name = serializers.SerializerMethodField()

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
            "issue_count",
            "done_issue_count",
            "resource_count",
            "progress",
            "progress_label",
            "lead_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "workspace_id", "status", "created_at", "updated_at"]

    def get_issue_count(self, obj: Project) -> int:
        return getattr(obj, "issue_count", None) if getattr(obj, "issue_count", None) is not None else obj.issues.count()

    def get_done_issue_count(self, obj: Project) -> int:
        value = getattr(obj, "done_issue_count", None)
        return value if value is not None else obj.issues.filter(status="done").count()

    def get_resource_count(self, obj: Project) -> int:
        value = getattr(obj, "resource_count", None)
        return value if value is not None else obj.resources.count()

    def get_progress(self, obj: Project) -> int:
        total = self.get_issue_count(obj)
        if not total:
            return 0
        return round(self.get_done_issue_count(obj) * 100 / total)

    def get_progress_label(self, obj: Project) -> str:
        total = self.get_issue_count(obj)
        done = self.get_done_issue_count(obj)
        return f"{done}/{total} 个 Issue 完成" if total else "暂无 Issue"

    def get_lead_name(self, obj: Project) -> str:
        if not obj.lead_type or not obj.lead_id:
            return "未指定"
        if obj.lead_type == Project.LeadType.MEMBER:
            member = obj.workspace.members.filter(id=obj.lead_id).select_related("user").first()
            return member.user.name if member else str(obj.lead_id)
        if obj.lead_type == Project.LeadType.AGENT:
            agent = obj.workspace.agents.filter(id=obj.lead_id).first()
            return agent.name if agent else str(obj.lead_id)
        return str(obj.lead_id)

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
