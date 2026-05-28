"""Issue, comment, label, and attachment API views."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction
from django.db.models import Max, Q, QuerySet
from django.http import Http404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import Workspace
from accounts.workspace_scope import (
    resolve_workspace_id,
    resolve_workspace_member,
    validate_actor_ref,
    validate_issue_id,
    validate_project_id,
)

from .models import (
    Attachment,
    Comment,
    CommentReaction,
    Issue,
    IssueDependency,
    IssueLabel,
    IssueSubscriber,
    IssueToLabel,
)
from .serializers import (
    AttachmentSerializer,
    CommentReactionSerializer,
    CommentResolveSerializer,
    CommentSerializer,
    IssueBatchUpdateSerializer,
    IssueCreateSerializer,
    IssueDependencySerializer,
    IssueLabelSerializer,
    IssueReorderSerializer,
    IssueSerializer,
    IssueSubscriberSerializer,
    IssueToLabelSerializer,
)


class WorkspaceScopedMixin:
    """Resolve workspace scope and enforce membership."""

    request: Request

    def get_workspace_id(self) -> UUID:
        return resolve_workspace_id(self.request)


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

    def _validate_issue_refs(self, attrs: dict) -> None:
        workspace_id = self.get_workspace_id()
        project = attrs.get("project")
        if project and project.workspace_id != workspace_id:
            raise ValidationError({"project": "Project must belong to the workspace."})
        parent_issue = attrs.get("parent_issue")
        if parent_issue and parent_issue.workspace_id != workspace_id:
            raise ValidationError({"parent_issue": "Parent issue must belong to the workspace."})
        assignee_type = attrs.get("assignee_type")
        assignee_id = attrs.get("assignee_id")
        if assignee_type or assignee_id:
            validate_actor_ref(assignee_type, assignee_id, workspace_id, required=True)

    def perform_create(self, serializer: IssueCreateSerializer) -> None:
        workspace_id = self.get_workspace_id()
        member = resolve_workspace_member(self.request, workspace_id)
        self._validate_issue_refs(serializer.validated_data)
        with transaction.atomic():
            workspace = Workspace.objects.select_for_update().get(id=workspace_id)
            max_existing_number = (
                Issue.objects.filter(workspace_id=workspace_id).aggregate(max_number=Max("number"))["max_number"]
                or 0
            )
            next_number = max(workspace.issue_counter, max_existing_number) + 1
            workspace.issue_counter = next_number
            workspace.save(update_fields=["issue_counter", "updated_at"])
            serializer.save(
                workspace_id=workspace_id,
                number=next_number,
                creator_type="member",
                creator_id=member.id,
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

    def perform_update(self, serializer: IssueSerializer) -> None:
        self._validate_issue_refs(serializer.validated_data)
        serializer.save()

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
        workspace_id = self.get_workspace_id()
        if project_id is not None:
            validate_project_id(project_id, workspace_id)
        if data.get("assignee_type") or data.get("assignee_id"):
            validate_actor_ref(data.get("assignee_type"), data.get("assignee_id"), workspace_id, required=True)
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
            id__in=ids, workspace_id=workspace_id
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
            validate_actor_ref(
                serializer.validated_data.get("subscriber_type"),
                serializer.validated_data.get("subscriber_id"),
                self.get_workspace_id(),
                required=True,
            )
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
            validate_actor_ref(subscriber_type, subscriber_id, self.get_workspace_id(), required=True)
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
            if serializer.validated_data["depends_on"].workspace_id != self.get_workspace_id():
                raise ValidationError({"depends_on": "Dependency issue must belong to the workspace."})
            serializer.save(issue=issue)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        elif request.method == "DELETE":
            dep_id = request.data.get("depends_on")
            if not dep_id:
                return Response(
                    {"detail": "depends_on is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            validate_issue_id(dep_id, self.get_workspace_id(), field_name="depends_on")
            IssueDependency.objects.filter(
                issue=issue, depends_on_id=dep_id
            ).delete()
            return Response({"ok": True})

    @action(detail=True, methods=["get", "post", "delete"], url_path="labels")
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
            mapping, created = IssueToLabel.objects.get_or_create(issue=issue, label=label)
            serializer = IssueToLabelSerializer(mapping)
            return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        elif request.method == "DELETE":
            label_id = request.data.get("label_id")
            if not label_id:
                return Response(
                    {"detail": "label_id is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            deleted, _ = IssueToLabel.objects.filter(
                issue=issue,
                label_id=label_id,
                label__workspace_id=self.get_workspace_id(),
            ).delete()
            return Response({"ok": True, "deleted": deleted})


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
        workspace_id = self.get_workspace_id()
        if issue_id:
            try:
                issue = Issue.objects.get(id=issue_id, workspace_id=workspace_id)
            except Issue.DoesNotExist:
                raise Http404("Issue not found")
        else:
            raise ValidationError({"issue_id": "issue_id URL parameter is required."})
        parent = serializer.validated_data.get("parent")
        if parent and (parent.workspace_id != workspace_id or parent.issue_id != issue.id):
            raise ValidationError({"parent": "Parent comment must belong to the same issue and workspace."})
        member = resolve_workspace_member(self.request, workspace_id)
        serializer.save(
            issue=issue,
            workspace_id=workspace_id,
            author_type="member",
            author_id=member.id,
        )

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request: Request, comment_id: UUID = None, **kwargs) -> Response:
        comment = self.get_object()
        serializer = CommentResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resolved_at = serializer.validated_data.get("resolved_at") or timezone.now()
        workspace_id = self.get_workspace_id()
        default_member = resolve_workspace_member(request, workspace_id)
        resolved_by_type = request.data.get("resolved_by_type", "member")
        resolved_by_id = request.data.get("resolved_by_id") or default_member.id
        validate_actor_ref(resolved_by_type, resolved_by_id, workspace_id, required=True)
        comment.resolved_at = resolved_at
        comment.resolved_by_type = resolved_by_type
        comment.resolved_by_id = resolved_by_id
        comment.save(update_fields=["resolved_at", "resolved_by_type", "resolved_by_id", "updated_at"])

        return Response(CommentSerializer(comment).data)

    @action(detail=True, methods=["get", "post"], url_path="reactions")
    def reactions(self, request: Request, comment_id: UUID = None, **kwargs) -> Response:
        comment = self.get_object()
        if request.method == "GET":
            reactions = CommentReaction.objects.filter(comment=comment)
            serializer = CommentReactionSerializer(reactions, many=True)
            return Response(serializer.data)
        elif request.method == "POST":
            serializer = CommentReactionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            validate_actor_ref(
                serializer.validated_data.get("actor_type"),
                serializer.validated_data.get("actor_id"),
                self.get_workspace_id(),
                required=True,
            )
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
        return Attachment.objects.filter(
            Q(issue__workspace_id=self.get_workspace_id()) | Q(comment__workspace_id=self.get_workspace_id())
        )

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issue = serializer.validated_data.get("issue")
        comment = serializer.validated_data.get("comment")
        workspace_id = self.get_workspace_id()
        if issue and issue.workspace_id != workspace_id:
            raise ValidationError({"issue": "Issue must belong to the workspace."})
        if comment and comment.workspace_id != workspace_id:
            raise ValidationError({"comment": "Comment must belong to the workspace."})
        validate_actor_ref(
            serializer.validated_data.get("uploader_type"),
            serializer.validated_data.get("uploader_id"),
            workspace_id,
            required=True,
        )
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
