"""Inbox, activity, and pin API views."""

from __future__ import annotations

from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Activity, InboxItem, Pin
from .serializers import (
    ActivitySerializer,
    CreatePinSerializer,
    InboxItemArchiveSerializer,
    InboxItemReadSerializer,
    InboxItemSerializer,
    PinSerializer,
    ReorderPinsSerializer,
)

User = get_user_model()


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


class InboxViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """Inbox items for a recipient within a workspace."""

    lookup_url_kwarg = "inbox_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "post", "head", "options"]
    serializer_class = InboxItemSerializer

    def get_queryset(self) -> QuerySet[InboxItem]:
        ws_id = self.get_workspace_id()
        qs = InboxItem.objects.filter(workspace_id=ws_id)
        # Filter by recipient — default to the authenticated user as member.
        recipient_type = self.request.query_params.get("recipient_type", "member")
        recipient_id = self.request.query_params.get("recipient_id") or str(self.request.user.id)
        qs = qs.filter(recipient_type=recipient_type, recipient_id=recipient_id)
        # Optional filters.
        if "type" in self.request.query_params:
            qs = qs.filter(type=self.request.query_params["type"])
        if "severity" in self.request.query_params:
            qs = qs.filter(severity=self.request.query_params["severity"])
        if "issue_id" in self.request.query_params:
            qs = qs.filter(issue_id=self.request.query_params["issue_id"])
        archived = self.request.query_params.get("archived", "false").lower() == "true"
        qs = qs.filter(archived=archived)
        return qs

    def list(self, request: Request, *args, **kwargs) -> Response:
        qs = self.get_queryset()
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", 50))
        total = qs.count()
        page = qs[offset : offset + limit]
        serializer = self.get_serializer(page, many=True)
        return Response({"items": serializer.data, "total": total})

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request: Request, inbox_id=None) -> Response:
        item = self.get_object()
        item.read = True
        item.save(update_fields=["read"])
        return Response(InboxItemSerializer(item).data)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request: Request, inbox_id=None) -> Response:
        item = self.get_object()
        item.archived = True
        item.save(update_fields=["archived"])
        return Response(InboxItemSerializer(item).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request: Request) -> Response:
        updated = self.get_queryset().filter(read=False).update(read=True)
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="archive-all")
    def archive_all(self, request: Request) -> Response:
        updated = self.get_queryset().filter(archived=False).update(archived=True)
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="archive-all-read")
    def archive_all_read(self, request: Request) -> Response:
        updated = (
            self.get_queryset()
            .filter(archived=False, read=True)
            .update(archived=True)
        )
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="archive-completed")
    def archive_completed(self, request: Request) -> Response:
        updated = (
            self.get_queryset()
            .filter(
                archived=False,
                type__in=[
                    InboxItem.Type.TASK_COMPLETED,
                    InboxItem.Type.TASK_FAILED,
                    InboxItem.Type.AGENT_COMPLETED,
                    InboxItem.Type.AGENT_BLOCKED,
                ],
            )
            .update(archived=True)
        )
        return Response({"updated": updated})

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        ws_id = self.get_workspace_id()
        recipient_type = request.query_params.get("recipient_type", "member")
        recipient_id = request.query_params.get("recipient_id") or str(request.user.id)
        count = InboxItem.objects.filter(
            workspace_id=ws_id,
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            read=False,
            archived=False,
        ).count()
        return Response({"count": count})


class ActivityViewSet(WorkspaceScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Issue / workspace activity log — read-only timeline."""

    lookup_url_kwarg = "activity_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    serializer_class = ActivitySerializer

    def get_queryset(self) -> QuerySet[Activity]:
        ws_id = self.get_workspace_id()
        qs = Activity.objects.filter(workspace_id=ws_id)
        if issue_id := self.request.query_params.get("issue_id"):
            qs = qs.filter(issue_id=issue_id)
        return qs

    def list(self, request: Request, *args, **kwargs) -> Response:
        qs = self.get_queryset()
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", 50))
        total = qs.count()
        page = qs[offset : offset + limit]
        serializer = self.get_serializer(page, many=True)
        return Response({"items": serializer.data, "total": total})


class PinViewSet(WorkspaceScopedMixin, viewsets.GenericViewSet):
    """User pins for workspace items."""

    serializer_class = PinSerializer

    def get_queryset(self) -> QuerySet[Pin]:
        ws_id = self.get_workspace_id()
        return Pin.objects.filter(workspace_id=ws_id, pinned_by=self.request.user)

    def list(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = CreatePinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item_type = serializer.validated_data["item_type"]
        item_id = serializer.validated_data["item_id"]
        ws_id = self.get_workspace_id()

        pin, created = Pin.objects.get_or_create(
            workspace_id=ws_id,
            item_type=item_type,
            item_id=item_id,
            pinned_by=request.user,
        )
        if not created:
            return Response(PinSerializer(pin).data, status=status.HTTP_200_OK)
        return Response(PinSerializer(pin).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["put"], url_path="reorder")
    def reorder(self, request: Request) -> Response:
        serializer = ReorderPinsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item_ids = serializer.validated_data["item_ids"]
        for idx, entry in enumerate(item_ids):
            Pin.objects.filter(
                workspace_id=self.get_workspace_id(),
                pinned_by=request.user,
                item_type=entry.get("item_type", ""),
                item_id=entry.get("item_id", ""),
            ).update(position=idx)
        return Response({"ok": True})

    @action(detail=False, methods=["delete"], url_path=r"(?P<item_type>[^/]+)/(?P<item_id>[0-9a-f-]{36})")
    def unpin(self, request: Request, item_type=None, item_id=None) -> Response:
        ws_id = self.get_workspace_id()
        deleted, _ = Pin.objects.filter(
            workspace_id=ws_id,
            pinned_by=request.user,
            item_type=item_type,
            item_id=item_id,
        ).delete()
        return Response({"ok": True})
