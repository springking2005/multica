"""Model creation tests for issues app."""

import uuid

import pytest
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import Workspace
from issues.models import (
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

pytestmark = pytest.mark.django_db


@pytest.fixture
def workspace() -> Workspace:
    slug = f"test-{uuid.uuid4().hex[:8]}"
    return Workspace.objects.create(name="Test Workspace", slug=slug)


class TestIssueModel:
    def test_create_issue_minimal(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Test Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        assert issue.id is not None
        assert isinstance(issue.id, uuid.UUID)
        assert issue.title == "Test Issue"
        assert issue.description == ""
        assert issue.status == Issue.Status.BACKLOG
        assert issue.priority == Issue.Priority.NONE
        assert issue.number == 0
        assert issue.position == 0.0
        assert issue.assignee_type is None
        assert issue.assignee_id is None
        assert issue.created_at is not None
        assert issue.updated_at is not None

    def test_create_issue_full(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Full Issue",
            description="A full description",
            number=42,
            status=Issue.Status.IN_PROGRESS,
            priority=Issue.Priority.HIGH,
            assignee_type=Issue.AssigneeType.AGENT,
            assignee_id=uuid.uuid4(),
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
            position=1.5,
            due_date=timezone.now(),
            origin_type=Issue.OriginType.AUTOPILOT,
            origin_id=uuid.uuid4(),
        )
        assert issue.title == "Full Issue"
        assert issue.description == "A full description"
        assert issue.number == 42
        assert issue.status == Issue.Status.IN_PROGRESS
        assert issue.priority == Issue.Priority.HIGH
        assert issue.assignee_type == Issue.AssigneeType.AGENT
        assert issue.assignee_id is not None
        assert issue.position == 1.5
        assert issue.due_date is not None
        assert issue.origin_type == Issue.OriginType.AUTOPILOT
        assert issue.origin_id is not None

    def test_issue_str(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="String Test",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        assert str(issue) == "String Test"

    def test_unique_workspace_number(self, workspace):
        Issue.objects.create(
            workspace=workspace,
            title="Issue 1",
            number=1,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        with pytest.raises(Exception):
            Issue.objects.create(
                workspace=workspace,
                title="Issue 2",
                number=1,
                creator_type=Issue.AssigneeType.MEMBER,
                creator_id=uuid.uuid4(),
            )

    def test_status_choices(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Status Test",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        for status in Issue.Status.values:
            issue.status = status
            issue.full_clean()
            issue.save()

    def test_priority_choices(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Priority Test",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        for priority in Issue.Priority.values:
            issue.priority = priority
            issue.full_clean()
            issue.save()

    def test_parent_child_relationship(self, workspace):
        parent = Issue.objects.create(
            workspace=workspace,
            title="Parent Issue",
            number=1,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        child = Issue.objects.create(
            workspace=workspace,
            title="Child Issue",
            number=2,
            parent_issue=parent,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        assert child.parent_issue == parent
        assert list(parent.children.all()) == [child]

    def test_parent_set_null_on_delete(self, workspace):
        parent = Issue.objects.create(
            workspace=workspace,
            title="Parent Issue",
            number=3,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        child = Issue.objects.create(
            workspace=workspace,
            title="Child Issue",
            number=4,
            parent_issue=parent,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        parent.delete()
        child.refresh_from_db()
        assert child.parent_issue is None


class TestCommentModel:
    def test_create_comment(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue with comment",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        comment = Comment.objects.create(
            issue=issue,
            workspace=workspace,
            author_type=Comment.AuthorType.MEMBER,
            author_id=uuid.uuid4(),
            content="This is a comment.",
        )
        assert comment.id is not None
        assert isinstance(comment.id, uuid.UUID)
        assert comment.issue == issue
        assert comment.content == "This is a comment."
        assert comment.type == Comment.Type.COMMENT
        assert comment.resolved_at is None
        assert comment.created_at is not None

    def test_comment_resolved_fields(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        comment = Comment.objects.create(
            issue=issue,
            workspace=workspace,
            author_type=Comment.AuthorType.MEMBER,
            author_id=uuid.uuid4(),
            content="Resolved comment",
            resolved_at=timezone.now(),
            resolved_by_type=Comment.AuthorType.MEMBER,
            resolved_by_id=uuid.uuid4(),
        )
        assert comment.resolved_at is not None
        assert comment.resolved_by_type == Comment.AuthorType.MEMBER
        assert comment.resolved_by_id is not None

    def test_comment_parent(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        parent = Comment.objects.create(
            issue=issue,
            workspace=workspace,
            author_type=Comment.AuthorType.MEMBER,
            author_id=uuid.uuid4(),
            content="Parent",
        )
        reply = Comment.objects.create(
            issue=issue,
            workspace=workspace,
            author_type=Comment.AuthorType.AGENT,
            author_id=uuid.uuid4(),
            content="Reply",
            parent=parent,
        )
        assert reply.parent == parent
        assert list(parent.replies.all()) == [reply]

    def test_comment_cascade_on_issue_delete(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        comment = Comment.objects.create(
            issue=issue,
            workspace=workspace,
            author_type=Comment.AuthorType.MEMBER,
            author_id=uuid.uuid4(),
            content="Will be deleted",
        )
        comment_id = comment.id
        issue.delete()
        assert not Comment.objects.filter(id=comment_id).exists()


class TestIssueSubscriberModel:
    def test_create_subscriber(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        sub = IssueSubscriber.objects.create(
            issue=issue,
            subscriber_type=IssueSubscriber.SubscriberType.MEMBER,
            subscriber_id=uuid.uuid4(),
        )
        assert sub.id is not None
        assert sub.issue == issue
        assert sub.subscriber_type == IssueSubscriber.SubscriberType.MEMBER

    def test_unique_subscriber_constraint(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        sub_id = uuid.uuid4()
        IssueSubscriber.objects.create(
            issue=issue,
            subscriber_type=IssueSubscriber.SubscriberType.MEMBER,
            subscriber_id=sub_id,
        )
        with pytest.raises(Exception):
            IssueSubscriber.objects.create(
                issue=issue,
                subscriber_type=IssueSubscriber.SubscriberType.MEMBER,
                subscriber_id=sub_id,
            )

    def test_subscriber_cascade_on_issue_delete(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        sub = IssueSubscriber.objects.create(
            issue=issue,
            subscriber_type=IssueSubscriber.SubscriberType.MEMBER,
            subscriber_id=uuid.uuid4(),
        )
        sub_id = sub.id
        issue.delete()
        assert not IssueSubscriber.objects.filter(id=sub_id).exists()


class TestIssueDependencyModel:
    def test_create_dependency(self, workspace):
        issue1 = Issue.objects.create(
            workspace=workspace,
            title="Issue 1",
            number=5,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        issue2 = Issue.objects.create(
            workspace=workspace,
            title="Issue 2",
            number=6,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        dep = IssueDependency.objects.create(
            issue=issue1,
            depends_on=issue2,
            type=IssueDependency.Type.BLOCKS,
        )
        assert dep.id is not None
        assert dep.issue == issue1
        assert dep.depends_on == issue2
        assert dep.type == IssueDependency.Type.BLOCKS

    def test_dependency_type_choices(self, workspace):
        issue1 = Issue.objects.create(
            workspace=workspace,
            title="Issue 1",
            number=7,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        issue2 = Issue.objects.create(
            workspace=workspace,
            title="Issue 2",
            number=8,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        for dep_type in IssueDependency.Type.values:
            dep = IssueDependency.objects.create(
                issue=issue1, depends_on=issue2, type=dep_type
            )
            dep.full_clean()

    def test_dependency_cascade(self, workspace):
        issue1 = Issue.objects.create(
            workspace=workspace,
            title="Issue 1",
            number=9,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        issue2 = Issue.objects.create(
            workspace=workspace,
            title="Issue 2",
            number=10,
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        dep = IssueDependency.objects.create(
            issue=issue1, depends_on=issue2, type=IssueDependency.Type.RELATED
        )
        dep_id = dep.id
        issue1.delete()
        assert not IssueDependency.objects.filter(id=dep_id).exists()


class TestIssueLabelModel:
    def test_create_label(self, workspace):
        label = IssueLabel.objects.create(
            workspace=workspace, name="bug", color="#FF0000"
        )
        assert label.id is not None
        assert label.name == "bug"
        assert label.color == "#FF0000"
        assert label.created_at is not None

    def test_default_color(self, workspace):
        label = IssueLabel.objects.create(workspace=workspace, name="feature")
        assert label.color == "#6B7280"

    def test_case_insensitive_unique(self, workspace):
        IssueLabel.objects.create(workspace=workspace, name="Bug")
        with pytest.raises(Exception):
            IssueLabel.objects.create(workspace=workspace, name="bug")


class TestIssueToLabelModel:
    def test_link_issue_to_label(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Labeled issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        label = IssueLabel.objects.create(workspace=workspace, name="bug")
        mapping = IssueToLabel.objects.create(issue=issue, label=label)
        assert mapping.issue == issue
        assert mapping.label == label

    def test_unique_link(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        label = IssueLabel.objects.create(workspace=workspace, name="bug")
        IssueToLabel.objects.create(issue=issue, label=label)
        with pytest.raises(Exception):
            IssueToLabel.objects.create(issue=issue, label=label)

    def test_cascade_on_issue_delete(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        label = IssueLabel.objects.create(workspace=workspace, name="bug")
        mapping = IssueToLabel.objects.create(issue=issue, label=label)
        mapping_id = mapping.id
        issue.delete()
        assert not IssueToLabel.objects.filter(id=mapping_id).exists()

    def test_cascade_on_label_delete(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        label = IssueLabel.objects.create(workspace=workspace, name="bug")
        mapping = IssueToLabel.objects.create(issue=issue, label=label)
        mapping_id = mapping.id
        label.delete()
        assert not IssueToLabel.objects.filter(id=mapping_id).exists()


class TestCommentReactionModel:
    def test_create_reaction(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        comment = Comment.objects.create(
            issue=issue,
            workspace=workspace,
            author_type=Comment.AuthorType.MEMBER,
            author_id=uuid.uuid4(),
            content="Reactable",
        )
        reaction = CommentReaction.objects.create(
            comment=comment,
            actor_type=Comment.AuthorType.MEMBER,
            actor_id=uuid.uuid4(),
            emoji="👍",
        )
        assert reaction.id is not None
        assert reaction.comment == comment
        assert reaction.emoji == "👍"

    def test_unique_reaction_constraint(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        comment = Comment.objects.create(
            issue=issue,
            workspace=workspace,
            author_type=Comment.AuthorType.MEMBER,
            author_id=uuid.uuid4(),
            content="Reactable",
        )
        actor_id = uuid.uuid4()
        CommentReaction.objects.create(
            comment=comment,
            actor_type=Comment.AuthorType.MEMBER,
            actor_id=actor_id,
            emoji="👍",
        )
        with pytest.raises(Exception):
            CommentReaction.objects.create(
                comment=comment,
                actor_type=Comment.AuthorType.MEMBER,
                actor_id=actor_id,
                emoji="👍",
            )

    def test_cascade_on_comment_delete(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        comment = Comment.objects.create(
            issue=issue,
            workspace=workspace,
            author_type=Comment.AuthorType.MEMBER,
            author_id=uuid.uuid4(),
            content="Reactable",
        )
        reaction = CommentReaction.objects.create(
            comment=comment,
            actor_type=Comment.AuthorType.MEMBER,
            actor_id=uuid.uuid4(),
            emoji="👍",
        )
        reaction_id = reaction.id
        comment.delete()
        assert not CommentReaction.objects.filter(id=reaction_id).exists()


class TestIssueReactionModel:
    def test_create_reaction(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        reaction = IssueReaction.objects.create(
            issue=issue,
            actor_type=Comment.AuthorType.MEMBER,
            actor_id=uuid.uuid4(),
            emoji="👎",
        )
        assert reaction.id is not None
        assert reaction.issue == issue
        assert reaction.emoji == "👎"

    def test_unique_reaction_constraint(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        actor_id = uuid.uuid4()
        IssueReaction.objects.create(
            issue=issue,
            actor_type=Comment.AuthorType.MEMBER,
            actor_id=actor_id,
            emoji="👎",
        )
        with pytest.raises(Exception):
            IssueReaction.objects.create(
                issue=issue,
                actor_type=Comment.AuthorType.MEMBER,
                actor_id=actor_id,
                emoji="👎",
            )

    def test_cascade_on_issue_delete(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        reaction = IssueReaction.objects.create(
            issue=issue,
            actor_type=Comment.AuthorType.MEMBER,
            actor_id=uuid.uuid4(),
            emoji="👎",
        )
        reaction_id = reaction.id
        issue.delete()
        assert not IssueReaction.objects.filter(id=reaction_id).exists()


class TestAttachmentModel:
    def test_create_attachment_on_issue(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        attachment = Attachment.objects.create(
            issue=issue,
            uploader_type=Attachment.UploaderType.MEMBER,
            uploader_id=uuid.uuid4(),
            url="https://example.com/file.pdf",
            filename="file.pdf",
            content_type="application/pdf",
            size_bytes=1024,
        )
        assert attachment.id is not None
        assert attachment.issue == issue
        assert attachment.comment is None
        assert attachment.filename == "file.pdf"
        assert attachment.size_bytes == 1024

    def test_create_attachment_on_comment(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        comment = Comment.objects.create(
            issue=issue,
            workspace=workspace,
            author_type=Comment.AuthorType.MEMBER,
            author_id=uuid.uuid4(),
            content="Comment with attachment",
        )
        attachment = Attachment.objects.create(
            comment=comment,
            uploader_type=Attachment.UploaderType.AGENT,
            uploader_id=uuid.uuid4(),
            url="https://example.com/image.png",
            filename="image.png",
            content_type="image/png",
            size_bytes=2048,
        )
        assert attachment.comment == comment
        assert attachment.issue is None

    def test_attachment_requires_target(self, workspace):
        with pytest.raises(IntegrityError):
            Attachment.objects.create(
                uploader_type=Attachment.UploaderType.MEMBER,
                uploader_id=uuid.uuid4(),
                url="https://example.com/file.pdf",
                filename="file.pdf",
                content_type="application/pdf",
                size_bytes=1024,
            )

    def test_cascade_on_issue_delete(self, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Issue",
            creator_type=Issue.AssigneeType.MEMBER,
            creator_id=uuid.uuid4(),
        )
        attachment = Attachment.objects.create(
            issue=issue,
            uploader_type=Attachment.UploaderType.MEMBER,
            uploader_id=uuid.uuid4(),
            url="https://example.com/file.pdf",
            filename="file.pdf",
            content_type="application/pdf",
            size_bytes=1024,
        )
        attachment_id = attachment.id
        issue.delete()
        assert not Attachment.objects.filter(id=attachment_id).exists()
