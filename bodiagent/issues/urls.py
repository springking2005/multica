"""Issue URL configuration — DRF router with nested routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttachmentViewSet,
    CommentViewSet,
    IssueLabelViewSet,
    IssueViewSet,
)


class NoTrailingSlashRouter(DefaultRouter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trailing_slash = ""


app_name = "issues"

router = NoTrailingSlashRouter()
router.register("issues", IssueViewSet, basename="issue")
router.register("labels", IssueLabelViewSet, basename="issuelabel")

issue_collection_slash = IssueViewSet.as_view({"get": "list", "post": "create"})
issue_task_cancel = IssueViewSet.as_view({"post": "cancel_issue_task"})
issue_task_messages = IssueViewSet.as_view({"get": "issue_task_messages"})

comment_list = CommentViewSet.as_view({"get": "list", "post": "create"})
comment_detail = CommentViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)
comment_resolve = CommentViewSet.as_view({"post": "resolve"})
comment_reactions = CommentViewSet.as_view({"get": "reactions", "post": "reactions"})

attachment_list = AttachmentViewSet.as_view({"post": "create"})
attachment_detail = AttachmentViewSet.as_view({"get": "retrieve", "delete": "destroy"})

urlpatterns = [
    path("issues/", issue_collection_slash, name="issue-list-slash"),
    path("", include(router.urls)),
    path(
        "issues/<uuid:issue_id>/tasks/<uuid:task_id>/cancel",
        issue_task_cancel,
        name="issue-task-cancel",
    ),
    path(
        "issues/<uuid:issue_id>/tasks/<uuid:task_id>/messages",
        issue_task_messages,
        name="issue-task-messages",
    ),
    # Comment routes nested under issues
    path(
        "issues/<uuid:issue_id>/comments",
        comment_list,
        name="issue-comment-list",
    ),
    path(
        "issues/<uuid:issue_id>/comments/<uuid:comment_id>",
        comment_detail,
        name="issue-comment-detail",
    ),
    path(
        "issues/<uuid:issue_id>/comments/<uuid:comment_id>/resolve",
        comment_resolve,
        name="issue-comment-resolve",
    ),
    path(
        "issues/<uuid:issue_id>/comments/<uuid:comment_id>/reactions",
        comment_reactions,
        name="issue-comment-reactions",
    ),
    # Attachment routes
    path(
        "attachments",
        attachment_list,
        name="attachment-list",
    ),
    path(
        "attachments/<uuid:attachment_id>",
        attachment_detail,
        name="attachment-detail",
    ),
]
