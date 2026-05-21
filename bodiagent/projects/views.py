"""Project API views."""

from __future__ import annotations

from uuid import UUID

from django.db.models import Count, Q, QuerySet
from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.workspace_scope import (
    resolve_workspace_id,
    validate_actor_ref,
    validate_issue_id,
    validate_project_id,
)

from .models import Project, ProjectResource
from .serializers import (
    ProjectResourceCreateSerializer,
    ProjectResourceSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
)


class WorkspaceScopedMixin:
    """Resolve workspace scope and enforce membership."""

    request: Request

    def get_workspace_id(self) -> UUID:
        return resolve_workspace_id(self.request)


class ProjectViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """CRUD and search for workspace projects."""

    lookup_url_kwarg = "project_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "post", "put", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Project]:
        return Project.objects.filter(workspace_id=self.get_workspace_id()).annotate(
            issue_count=Count("issues", distinct=True),
            done_issue_count=Count("issues", filter=Q(issues__status="done"), distinct=True),
            resource_count=Count("resources", distinct=True),
        )

    def get_serializer_class(self):
        if self.action in {"update", "partial_update"}:
            return ProjectUpdateSerializer
        return ProjectSerializer

    def _validate_project_refs(self, attrs: dict) -> None:
        if attrs.get("lead_type") or attrs.get("lead_id"):
            validate_actor_ref(
                attrs.get("lead_type"),
                attrs.get("lead_id"),
                self.get_workspace_id(),
                required=True,
            )

    def perform_create(self, serializer: ProjectSerializer) -> None:
        self._validate_project_refs(serializer.validated_data)
        serializer.save(workspace_id=self.get_workspace_id())

    def perform_update(self, serializer: ProjectSerializer) -> None:
        self._validate_project_refs(serializer.validated_data)
        serializer.save()

    def list(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    def update(self, request: Request, *args, **kwargs) -> Response:
        kwargs["partial"] = False
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request: Request) -> Response:
        query = request.query_params.get("q", "").strip()
        queryset = self.get_queryset()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(icon__icontains=query)
                | Q(priority__icontains=query)
                | Q(status__icontains=query)
            )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ProjectResourceViewSet(WorkspaceScopedMixin, viewsets.GenericViewSet):
    """Nested project resources."""

    lookup_url_kwarg = "resource_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    serializer_class = ProjectResourceSerializer

    def get_project(self) -> Project:
        try:
            return Project.objects.get(id=self.kwargs["project_id"], workspace_id=self.get_workspace_id())
        except Project.DoesNotExist as exc:
            raise Http404 from exc

    def get_queryset(self) -> QuerySet[ProjectResource]:
        return ProjectResource.objects.filter(project=self.get_project(), workspace_id=self.get_workspace_id())

    def list(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        project = self.get_project()
        serializer = ProjectResourceCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        resource_type = serializer.validated_data.get("resource_type")
        resource_ref = serializer.validated_data.get("resource_ref") or {}
        resource_id = resource_ref.get("id") if isinstance(resource_ref, dict) else None
        if resource_type == "issue":
            validate_issue_id(resource_id, project.workspace_id, field_name="resource_id", required=True)
        elif resource_type == "project":
            validate_project_id(resource_id, project.workspace_id, field_name="resource_id", required=True)
        elif resource_type in {"member", "agent"}:
            validate_actor_ref(resource_type, resource_id, project.workspace_id, required=True)
        instance = serializer.save(project=project, workspace_id=project.workspace_id)
        return Response(ProjectResourceSerializer(instance).data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})
