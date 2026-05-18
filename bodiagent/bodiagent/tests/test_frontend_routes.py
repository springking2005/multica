import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from accounts.models import Member, Workspace


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        email="frontend@example.com",
        password="password",
        name="Frontend User",
    )


@pytest.fixture
def workspace(user):
    workspace = Workspace.objects.create(name="Frontend", slug="frontend")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    return workspace


@pytest.fixture
def authenticated_client(user, workspace):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def authenticated_client_without_workspace(user):
    client = Client()
    client.force_login(user)
    return client


def page_actions(body: str) -> str:
    match = re.search(r'<div class="ba-page-actions">(.*?)</div>', body, re.DOTALL)
    return match.group(1) if match else ""


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/agents/", "id=\"agent-page\""),
        ("/projects/", "id=\"project-page\""),
        ("/autopilots/", "id=\"autopilot-page\""),
        ("/settings/tokens/", "id=\"token-page\""),
    ],
)
def test_frontend_crud_pages_render(authenticated_client, workspace, path, marker):
    response = authenticated_client.get(path)

    assert response.status_code == 200
    body = response.content.decode()
    assert marker in body
    assert str(workspace.id) in body


@pytest.mark.parametrize(
    "path",
    ["/agents/", "/projects/", "/autopilots/", "/settings/tokens/"],
)
def test_frontend_crud_pages_require_login(path):
    response = Client().get(path)

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


def test_dashboard_renders_workspace_project_and_issue_actions(authenticated_client):
    response = authenticated_client.get("/dashboard/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "创建工作区" in body
    assert 'onclick="openWorkspaceDialog()"' in body
    assert 'href="/projects/?quick_create=1"' in body
    assert "创建项目" in body
    assert 'href="/issues?quick_create=1"' in body
    assert "创建 Issue" in body


def test_dashboard_without_workspace_renders_workspace_empty_state_action(
    authenticated_client_without_workspace,
):
    response = authenticated_client_without_workspace.get("/dashboard/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "创建或加入工作区后，这里会显示 Issue、智能体和收件箱动态。" in body
    assert 'onclick="openWorkspaceDialog()"' in body
    assert "创建工作区" in body


def test_projects_without_workspace_prompts_workspace_creation(
    authenticated_client_without_workspace,
):
    response = authenticated_client_without_workspace.get("/projects/")

    assert response.status_code == 200
    body = response.content.decode()
    actions = page_actions(body)
    assert "创建工作区" in actions
    assert 'onclick="openWorkspaceDialog()"' in actions
    assert "新建项目" not in actions
    assert "请先创建工作区，然后就可以创建项目。" in body


def test_projects_with_workspace_renders_project_creation_action(authenticated_client):
    response = authenticated_client.get("/projects/")

    assert response.status_code == 200
    body = response.content.decode()
    actions = page_actions(body)
    assert "新建项目" in actions
    assert 'onclick="openProjectForm()"' in actions
