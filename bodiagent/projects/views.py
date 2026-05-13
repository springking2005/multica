"""Project API views."""

from __future__ import annotations

from uuid import UUID

from django.db.models import Q, QuerySet
from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Project, ProjectResource
from .serializers import ProjectResourceCreateSerializer, ProjectResourceSerializer, ProjectSerializer, ProjectUpdateSerializer


class WorkspaceScopedMixin:
    """Resolve workspace scope from middleware/header/query."""

    request: Request

    def get_workspace_id(self) -> UUID:
        raw_workspace_id = (
            getattr(self.request, "workspace_id", None)
            or self.request.headers.get("X-Workspace-ID")
            or self.request.query_params.get("ws_id")
        )
        if not raw_workspace_id:
            raise ValidationError({"workspace_id": "X-Workspace-ID header or ws_id query parameter is required."})
        try:
            return UUID(str(raw_workspace_id))
        except ValueError as exc:
            raise ValidationError({"workspace_id": "Workspace id must be a valid UUID."}) from exc


class ProjectViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """CRUD and search for workspace projects."""

    lookup_url_kwarg = "project_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "post", "put", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Project]:
        return Project.objects.filter(workspace_id=self.get_workspace_id())

    def get_serializer_class(self):
        if self.action in {"update", "partial_update"}:
            return ProjectUpdateSerializer
        return ProjectSerializer

    def perform_create(self, serializer: ProjectSerializer) -> None:
        serializer.save(workspace_id=self.get_workspace_id())

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
        instance = serializer.save(project=project, workspace_id=project.workspace_id)
        return Response(ProjectResourceSerializer(instance).data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})
