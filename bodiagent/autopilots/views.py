"""Autopilot API views."""

from __future__ import annotations

from uuid import UUID

from django.db.models import QuerySet
from django.http import Http404
from rest_framework import pagination, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import Member
from accounts.workspace_scope import resolve_workspace_id, validate_actor_ref

from .models import Autopilot, AutopilotRun, AutopilotTrigger
from .serializers import (
    AutopilotCreateSerializer,
    AutopilotRunSerializer,
    AutopilotSerializer,
    AutopilotTriggerCreateSerializer,
    AutopilotTriggerSerializer,
    AutopilotTriggerUpdateSerializer,
    ManualTriggerSerializer,
)
from .services import AutopilotService


class CreatedAtCursorPagination(pagination.CursorPagination):
    ordering = "-created_at"


class WorkspaceScopedMixin:
    """Resolve workspace scope and enforce membership."""

    request: Request

    def get_workspace_id(self) -> UUID:
        return resolve_workspace_id(self.request)


class AutopilotViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """CRUD, enable/disable, manual trigger, list runs."""

    lookup_url_kwarg = "autopilot_id"
    pagination_class = CreatedAtCursorPagination
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Autopilot]:
        return Autopilot.objects.filter(
            workspace_id=self.get_workspace_id()
        ).prefetch_related("triggers")

    def get_serializer_class(self):
        if self.action == "create":
            return AutopilotCreateSerializer
        return AutopilotSerializer

    def _validate_autopilot_refs(self, attrs: dict) -> None:
        workspace_id = self.get_workspace_id()
        assignee = attrs.get("assignee")
        if assignee and assignee.workspace_id != workspace_id:
            raise ValidationError({"assignee": "Assignee must belong to the workspace."})
        created_by_type = attrs.get("created_by_type")
        created_by_id = attrs.get("created_by_id")
        if created_by_type or created_by_id:
            validate_actor_ref(created_by_type, created_by_id, workspace_id, required=True)

    def perform_create(self, serializer: AutopilotCreateSerializer) -> None:
        workspace_id = self.get_workspace_id()
        self._validate_autopilot_refs(serializer.validated_data)
        membership = Member.objects.filter(workspace_id=workspace_id, user=self.request.user).first()
        defaults = {"workspace_id": workspace_id}
        if membership is not None:
            defaults.update(created_by_type="member", created_by_id=membership.id)
        serializer.save(**defaults)

    def perform_update(self, serializer: AutopilotCreateSerializer) -> None:
        self._validate_autopilot_refs(serializer.validated_data)
        serializer.save()

    def update(self, request: Request, *args, **kwargs) -> Response:
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})

    @action(detail=True, methods=["post"], url_path="enable")
    def enable(self, request: Request, autopilot_id: UUID = None) -> Response:
        autopilot = self.get_object()
        autopilot.status = Autopilot.Status.ACTIVE
        autopilot.save(update_fields=["status", "updated_at"])
        return Response(AutopilotSerializer(autopilot).data)

    @action(detail=True, methods=["post"], url_path="disable")
    def disable(self, request: Request, autopilot_id: UUID = None) -> Response:
        autopilot = self.get_object()
        autopilot.status = Autopilot.Status.PAUSED
        autopilot.save(update_fields=["status", "updated_at"])
        return Response(AutopilotSerializer(autopilot).data)

    @action(detail=True, methods=["post"], url_path="trigger")
    def trigger_manual(self, request: Request, autopilot_id: UUID = None) -> Response:
        autopilot = self.get_object()
        serializer = ManualTriggerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run = AutopilotService.create_run(
            autopilot=autopilot,
            source=AutopilotRun.Source.MANUAL,
            trigger_payload=request.data,
        )
        AutopilotService.create_issue_for_run(run)
        AutopilotService.dispatch_task(run)

        run.refresh_from_db()
        return Response(
            AutopilotRunSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="runs")
    def list_runs(self, request: Request, autopilot_id: UUID = None) -> Response:
        autopilot = self.get_object()
        runs = AutopilotRun.objects.filter(autopilot=autopilot).order_by("-created_at")
        page = self.paginate_queryset(runs)
        if page is not None:
            serializer = AutopilotRunSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = AutopilotRunSerializer(runs, many=True)
        return Response(serializer.data)


class AutopilotTriggerViewSet(WorkspaceScopedMixin, viewsets.GenericViewSet):
    """Create, update, delete triggers for an autopilot."""

    lookup_url_kwarg = "trigger_id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self) -> QuerySet[AutopilotTrigger]:
        return AutopilotTrigger.objects.filter(
            autopilot__workspace_id=self.get_workspace_id()
        )

    def _get_autopilot(self) -> Autopilot:
        autopilot_id = self.kwargs.get("autopilot_id")
        try:
            return Autopilot.objects.get(
                id=autopilot_id, workspace_id=self.get_workspace_id()
            )
        except Autopilot.DoesNotExist:
            raise Http404("Autopilot not found")

    def create(self, request: Request, *args, **kwargs) -> Response:
        autopilot = self._get_autopilot()
        serializer = AutopilotTriggerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trigger = serializer.save(autopilot=autopilot)
        return Response(
            AutopilotTriggerSerializer(trigger).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        autopilot = self._get_autopilot()
        trigger = self.get_object()
        if trigger.autopilot_id != autopilot.id:
            raise Http404("Trigger not found for this autopilot")
        serializer = AutopilotTriggerUpdateSerializer(
            trigger, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AutopilotTriggerSerializer(trigger).data)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        autopilot = self._get_autopilot()
        trigger = self.get_object()
        if trigger.autopilot_id != autopilot.id:
            raise Http404("Trigger not found for this autopilot")
        trigger.delete()
        return Response({"ok": True})


class AutopilotRunViewSet(WorkspaceScopedMixin, viewsets.GenericViewSet):
    """List runs by autopilot, retrieve run detail."""

    lookup_url_kwarg = "run_id"
    pagination_class = CreatedAtCursorPagination
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self) -> QuerySet[AutopilotRun]:
        return AutopilotRun.objects.filter(
            autopilot__workspace_id=self.get_workspace_id()
        ).select_related("autopilot", "trigger")

    def list(self, request: Request, *args, **kwargs) -> Response:
        autopilot_id = self.kwargs.get("autopilot_id")
        runs = self.get_queryset().filter(
            autopilot_id=autopilot_id,
            autopilot__workspace_id=self.get_workspace_id(),
        ).order_by("-created_at")
        page = self.paginate_queryset(runs)
        if page is not None:
            serializer = AutopilotRunSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = AutopilotRunSerializer(runs, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        serializer = AutopilotRunSerializer(instance)
        return Response(serializer.data)
