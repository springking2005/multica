"""Basic model creation tests for Project and ProjectResource."""

import uuid

import pytest

from accounts.models import Workspace
from projects.models import Project, ProjectResource


@pytest.fixture
def workspace() -> Workspace:
    slug = f"test-{uuid.uuid4().hex[:8]}"
    return Workspace.objects.create(name="Test Workspace", slug=slug)


@pytest.mark.django_db
class TestProjectModel:
    def test_create_project_minimal(self, workspace):
        project = Project.objects.create(workspace=workspace, title="Test Project")
        assert project.id is not None
        assert isinstance(project.id, uuid.UUID)
        assert project.title == "Test Project"
        assert project.description == ""
        assert project.icon == "folder"
        assert project.status == Project.Status.PLANNED
        assert project.priority == Project.Priority.NONE
        assert project.lead_type is None
        assert project.lead_id is None
        assert project.created_at is not None
        assert project.updated_at is not None

    def test_create_project_full(self, workspace):
        project = Project.objects.create(
            workspace=workspace,
            title="Full Project",
            description="A project with all fields",
            icon="rocket",
            status=Project.Status.IN_PROGRESS,
            lead_type=Project.LeadType.MEMBER,
            lead_id=uuid.uuid4(),
            priority=Project.Priority.HIGH,
        )
        assert project.title == "Full Project"
        assert project.description == "A project with all fields"
        assert project.icon == "rocket"
        assert project.status == Project.Status.IN_PROGRESS
        assert project.lead_type == Project.LeadType.MEMBER
        assert project.lead_id is not None
        assert project.priority == Project.Priority.HIGH

    def test_project_str(self, workspace):
        project = Project.objects.create(workspace=workspace, title="String Test")
        assert str(project) == "String Test"

    def test_project_status_choices(self, workspace):
        project = Project.objects.create(workspace=workspace, title="Status Test")
        for status in Project.Status.values:
            project.status = status
            project.full_clean()
            project.save()

    def test_project_priority_choices(self, workspace):
        project = Project.objects.create(workspace=workspace, title="Priority Test")
        for priority in Project.Priority.values:
            project.priority = priority
            project.full_clean()
            project.save()

    def test_project_ordering(self, workspace):
        p1 = Project.objects.create(workspace=workspace, title="Older")
        p2 = Project.objects.create(workspace=workspace, title="Newer")
        projects = list(Project.objects.all())
        assert projects[0] == p2
        assert projects[1] == p1


@pytest.mark.django_db
class TestProjectResourceModel:
    def test_create_resource_minimal(self, workspace):
        project = Project.objects.create(
            workspace=workspace, title="Resource Project"
        )
        resource = ProjectResource.objects.create(
            project=project,
            workspace_id=workspace.id,
            resource_type="issue",
            resource_ref={"id": str(uuid.uuid4())},
        )
        assert resource.id is not None
        assert isinstance(resource.id, uuid.UUID)
        assert resource.project == project
        assert resource.resource_type == "issue"
        assert isinstance(resource.resource_ref, dict)
        assert resource.created_at is not None

    def test_create_resource_with_label(self, workspace):
        project = Project.objects.create(workspace=workspace, title="Label Project")
        resource = ProjectResource.objects.create(
            project=project,
            workspace_id=workspace.id,
            resource_type="document",
            resource_ref={"url": "https://example.com/doc"},
            label="Reference doc",
            position=1,
        )
        assert resource.label == "Reference doc"
        assert resource.position == 1

    def test_resource_str(self, workspace):
        project = Project.objects.create(workspace=workspace, title="Str Project")
        resource = ProjectResource.objects.create(
            project=project,
            workspace_id=workspace.id,
            resource_type="issue",
            resource_ref={"id": str(uuid.uuid4())},
        )
        assert str(resource).startswith("issue:")

    def test_resource_cascade_delete(self, workspace):
        project = Project.objects.create(workspace=workspace, title="Cascade Project")
        resource = ProjectResource.objects.create(
            project=project,
            workspace_id=workspace.id,
            resource_type="issue",
            resource_ref={"id": str(uuid.uuid4())},
        )
        resource_id = resource.id
        project.delete()
        assert not ProjectResource.objects.filter(id=resource_id).exists()

    def test_resource_unique_ref_constraint(self, workspace):
        project = Project.objects.create(workspace=workspace, title="Unique Project")
        ref = {"id": str(uuid.uuid4())}
        ProjectResource.objects.create(
            project=project,
            workspace_id=workspace.id,
            resource_type="issue",
            resource_ref=ref,
        )
        with pytest.raises(Exception):
            ProjectResource.objects.create(
                project=project,
                workspace_id=workspace.id,
                resource_type="issue",
                resource_ref=ref,
            )
