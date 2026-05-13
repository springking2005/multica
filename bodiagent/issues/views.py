"""Issue, comment, label, and attachment API views."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import Http404, FileResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

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
from .serializers import (
    AttachmentSerializer,
    CommentReactionSerializer,
    CommentResolveSerializer,
    CommentSerializer,
    IssueBatchUpdateSerializer,
    IssueChildrenSerializer,
    IssueCreateSerializer,
    IssueDependencySerializer,
    IssueLabelSerializer,
    IssueReactionSerializer,
    IssueReorderSerializer,
    IssueSerializer,
    IssueSubscriberSerializer,
    IssueToLabelSerializer,
)


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
            raise ValidationError(
                {"workspace_id": "X-Workspace-ID header or ws_id query parameter is required."}
            )
        try:
            return UUID(str(raw_workspace_id))
        except ValueError as exc:
            raise ValidationError(
                {"workspace_id": "Workspace id must be a valid UUID."}
            ) from exc


class IssueViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """CRUD, search, filter, batch-update, reorder, children, subscribers, dependencies."""

    lookup_url_kwarg = "issue_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Issue]:
        return Issue.objects.filter(workspace_id=self.get_workspace_id())

    def get_serializer_class(self):
        if self.action == "create":
            return IssueCreateSerializer
        return IssueSerializer

    def perform_create(self, serializer: IssueCreateSerializer) -> None:
        serializer.save(
            workspace_id=self.get_workspace_id(),
            creator_type="user",
            creator_id=self.request.user.id,
        )

    def list(self, request: Request, *args, **kwargs) -> Response:
        queryset = self.get_queryset()

        # Filtering
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status__in=status_filter.split(","))

        priority_filter = request.query_params.get("priority")
        if priority_filter:
            queryset = queryset.filter(priority__in=priority_filter.split(","))

        assignee_type = request.query_params.get("assignee_type")
        if assignee_type:
            queryset = queryset.filter(assignee_type=assignee_type)

        assignee_id = request.query_params.get("assignee_id")
        if assignee_id:
            queryset = queryset.filter(assignee_id=assignee_id)

        project_id = request.query_params.get("project_id")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        parent_issue_id = request.query_params.get("parent_issue_id")
        if parent_issue_id:
            queryset = queryset.filter(parent_issue_id=parent_issue_id)

        # Search
        search = request.query_params.get("search") or request.query_params.get("q", "")
        if search.strip():
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        # Ordering
        ordering = request.query_params.get("ordering", "-created_at")
        allowed = [
            "position", "-position", "created_at", "-created_at",
            "updated_at", "-updated_at", "priority", "-priority",
        ]
        if ordering in allowed:
            queryset = queryset.order_by(ordering)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def update(self, request: Request, *args, **kwargs) -> Response:
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="batch-update")
    def batch_update(self, request: Request) -> Response:
        serializer = IssueBatchUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ids = data.pop("ids")
        project_id = data.pop("project_id", None)
        update_fields = {}

        for key, value in data.items():
            if value is not None:
                update_fields[key] = value
        if project_id is not None:
            update_fields["project_id"] = project_id

        if not update_fields:
            return Response(
                {"detail": "No fields to update."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = Issue.objects.filter(
            id__in=ids, workspace_id=self.get_workspace_id()
        ).update(**update_fields)
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder(self, request: Request) -> Response:
        serializer = IssueReorderSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        items = {item["issue_id"]: item["position"] for item in serializer.validated_data}

        existing = Issue.objects.filter(
            id__in=list(items.keys()), workspace_id=self.get_workspace_id()
        )
        existing_ids = set(str(i.id) for i in existing)

        with transaction.atomic():
            updated = 0
            for issue in existing:
                new_pos = items.get(issue.id)
                if new_pos is not None and new_pos != issue.position:
                    issue.position = new_pos
                    issue.save(update_fields=["position", "updated_at"])
                    updated += 1

        return Response({"updated": updated})

    @action(detail=True, methods=["get"], url_path="children")
    def children(self, request: Request, issue_id: UUID = None) -> Response:
        issue = self.get_object()
        children = Issue.objects.filter(parent_issue=issue, workspace_id=self.get_workspace_id())
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post", "delete"], url_path="subscribers")
    def subscribers(self, request: Request, issue_id: UUID = None) -> Response:
        issue = self.get_object()
        if request.method == "GET":
            subs = IssueSubscriber.objects.filter(issue=issue)
            serializer = IssueSubscriberSerializer(subs, many=True)
            return Response(serializer.data)
        elif request.method == "POST":
            serializer = IssueSubscriberSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(issue=issue)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        elif request.method == "DELETE":
            subscriber_type = request.data.get("subscriber_type")
            subscriber_id = request.data.get("subscriber_id")
            if not subscriber_type or not subscriber_id:
                return Response(
                    {"detail": "subscriber_type and subscriber_id are required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            IssueSubscriber.objects.filter(
                issue=issue,
                subscriber_type=subscriber_type,
                subscriber_id=subscriber_id,
            ).delete()
            return Response({"ok": True})

    @action(detail=True, methods=["get", "post", "delete"], url_path="dependencies")
    def dependencies(self, request: Request, issue_id: UUID = None) -> Response:
        issue = self.get_object()
        if request.method == "GET":
            deps = IssueDependency.objects.filter(issue=issue)
            serializer = IssueDependencySerializer(deps, many=True)
            return Response(serializer.data)
        elif request.method == "POST":
            serializer = IssueDependencySerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(issue=issue)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        elif request.method == "DELETE":
            dep_id = request.data.get("depends_on")
            if not dep_id:
                return Response(
                    {"detail": "depends_on is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            IssueDependency.objects.filter(
                issue=issue, depends_on_id=dep_id
            ).delete()
            return Response({"ok": True})

    @action(detail=True, methods=["get", "post"], url_path="labels")
    def labels(self, request: Request, issue_id: UUID = None) -> Response:
        issue = self.get_object()
        if request.method == "GET":
            labels = IssueToLabel.objects.filter(issue=issue)
            serializer = IssueToLabelSerializer(labels, many=True)
            return Response(serializer.data)
        elif request.method == "POST":
            label_id = request.data.get("label_id")
            if not label_id:
                return Response(
                    {"detail": "label_id is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                label = IssueLabel.objects.get(
                    id=label_id, workspace_id=self.get_workspace_id()
                )
            except IssueLabel.DoesNotExist:
                raise Http404("Label not found")
            mapping = IssueToLabel.objects.create(issue=issue, label=label)
            serializer = IssueToLabelSerializer(mapping)
            return Response(serializer.data, status=status.HTTP_201_CREATED)


class CommentViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """CRUD, resolve, and reactions for comments."""

    lookup_url_kwarg = "comment_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]
    serializer_class = CommentSerializer

    def get_queryset(self) -> QuerySet[Comment]:
        return Comment.objects.filter(workspace_id=self.get_workspace_id())

    def perform_create(self, serializer: CommentSerializer) -> None:
        issue_id = self.kwargs.get("issue_id")
        if issue_id:
            try:
                issue = Issue.objects.get(
                    id=issue_id, workspace_id=self.get_workspace_id()
                )
            except Issue.DoesNotExist:
                raise Http404("Issue not found")
        else:
            raise ValidationError({"issue_id": "issue_id URL parameter is required."})
        serializer.save(
            issue=issue,
            workspace_id=self.get_workspace_id(),
            author_type="user",
            author_id=self.request.user.id,
        )

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request: Request, comment_id: UUID = None) -> Response:
        comment = self.get_object()
        serializer = CommentResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resolved_at = serializer.validated_data.get("resolved_at") or timezone.now()
        comment.resolved_at = resolved_at
        comment.resolved_by_type = request.data.get("resolved_by_type", "member")
        comment.resolved_by_id = request.data.get("resolved_by_id")
        comment.save(update_fields=["resolved_at", "resolved_by_type", "resolved_by_id", "updated_at"])

        return Response(CommentSerializer(comment).data)

    @action(detail=True, methods=["get", "post"], url_path="reactions")
    def reactions(self, request: Request, comment_id: UUID = None) -> Response:
        comment = self.get_object()
        if request.method == "GET":
            reactions = CommentReaction.objects.filter(comment=comment)
            serializer = CommentReactionSerializer(reactions, many=True)
            return Response(serializer.data)
        elif request.method == "POST":
            serializer = CommentReactionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(comment=comment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)


class IssueLabelViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """CRUD for workspace labels."""

    lookup_url_kwarg = "label_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]
    serializer_class = IssueLabelSerializer

    def get_queryset(self) -> QuerySet[IssueLabel]:
        return IssueLabel.objects.filter(workspace_id=self.get_workspace_id())

    def perform_create(self, serializer: IssueLabelSerializer) -> None:
        serializer.save(workspace_id=self.get_workspace_id())

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})


class AttachmentViewSet(WorkspaceScopedMixin, viewsets.GenericViewSet):
    """Upload, download, and delete attachments."""

    lookup_url_kwarg = "attachment_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    serializer_class = AttachmentSerializer

    def get_queryset(self) -> QuerySet[Attachment]:
        return Attachment.objects.all()

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(
            AttachmentSerializer(instance).data, status=status.HTTP_201_CREATED
        )

    def retrieve(self, request: Request, attachment_id: UUID = None) -> Response:
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})
