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
    assert response["Location"].startswith("/accounts/login/")
