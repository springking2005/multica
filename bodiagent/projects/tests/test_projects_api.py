import uuid

import pytest
from rest_framework.test import APIClient

from accounts.models import User, Workspace
from projects.models import Project, ProjectResource


@pytest.fixture
def api_client() -> APIClient:
    client = APIClient()
    user = User.objects.create_user(email=f"{uuid.uuid4()}@example.com", password="password", name="Tester")
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def workspace() -> Workspace:
    suffix = uuid.uuid4().hex[:8]
    return Workspace.objects.create(name=f"Workspace {suffix}", slug=f"workspace-{suffix}")


def test_project_crud_and_search(api_client: APIClient, workspace: Workspace):
    response = api_client.post(
        "/api/projects",
        {
            "title": "Launch automation",
            "icon": "rocket",
            "lead_type": "member",
            "lead_id": str(uuid.uuid4()),
            "priority": "high",
        },
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert response.status_code == 201
    project_id = response.data["id"]
    assert response.data["title"] == "Launch automation"
    assert response.data["status"] == "planned"

    list_response = api_client.get("/api/projects", HTTP_X_WORKSPACE_ID=str(workspace.id))
    assert list_response.status_code == 200
    assert [project["id"] for project in list_response.data] == [project_id]

    search_response = api_client.get("/api/projects/search?q=launch", HTTP_X_WORKSPACE_ID=str(workspace.id))
    assert search_response.status_code == 200
    assert [project["id"] for project in search_response.data] == [project_id]

    update_response = api_client.put(
        f"/api/projects/{project_id}",
        {
            "title": "Launch automation v2",
            "icon": "rocket",
            "status": "in_progress",
            "lead_type": "member",
            "lead_id": response.data["lead_id"],
            "priority": "urgent",
        },
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )
    assert update_response.status_code == 200
    assert update_response.data["status"] == "in_progress"
    assert update_response.data["priority"] == "urgent"

    delete_response = api_client.delete(f"/api/projects/{project_id}", HTTP_X_WORKSPACE_ID=str(workspace.id))
    assert delete_response.status_code == 200
    assert Project.objects.filter(id=project_id).exists() is False


def test_projects_are_workspace_scoped(api_client: APIClient):
    workspace_a = Workspace.objects.create(name="A", slug=f"a-{uuid.uuid4().hex[:8]}")
    workspace_b = Workspace.objects.create(name="B", slug=f"b-{uuid.uuid4().hex[:8]}")
    project = Project.objects.create(workspace=workspace_a, title="Scoped")
    Project.objects.create(workspace=workspace_b, title="Hidden")

    response = api_client.get("/api/projects", HTTP_X_WORKSPACE_ID=str(workspace_a.id))

    assert response.status_code == 200
    assert [item["id"] for item in response.data] == [str(project.id)]


def test_project_resource_round_trips_resource_id(api_client: APIClient, workspace: Workspace):
    project = Project.objects.create(workspace=workspace, title="Project")
    issue_id = uuid.uuid4()

    create_response = api_client.post(
        f"/api/projects/{project.id}/resources",
        {"resource_type": "issue", "resource_id": str(issue_id), "label": "Primary issue"},
        format="json",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert create_response.status_code == 201
    assert create_response.data["resource_id"] == str(issue_id)
    assert create_response.data["resource_ref"] == {"id": str(issue_id)}

    list_response = api_client.get(f"/api/projects/{project.id}/resources", HTTP_X_WORKSPACE_ID=str(workspace.id))
    assert list_response.status_code == 200
    assert list_response.data[0]["resource_id"] == str(issue_id)

    resource_id = create_response.data["id"]
    delete_response = api_client.delete(
        f"/api/projects/{project.id}/resources/{resource_id}",
        HTTP_X_WORKSPACE_ID=str(workspace.id),
    )

    assert delete_response.status_code == 200
    assert ProjectResource.objects.filter(id=resource_id).exists() is False


def test_workspace_header_is_required(api_client: APIClient):
    response = api_client.get("/api/projects")

    assert response.status_code == 400
    assert "workspace_id" in response.data
