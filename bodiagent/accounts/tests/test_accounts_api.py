import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Invitation, Member, PersonalAccessToken, Workspace


pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_verify_code_creates_user_and_returns_token(dev_verification_code):
    client = APIClient()

    response = client.post(
        "/auth/verify-code",
        {"email": "Ada@example.com", "code": dev_verification_code},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["token"]
    assert response.data["user"]["email"] == "Ada@example.com".lower()


def test_workspace_create_adds_owner_membership():
    user = get_user_model().objects.create_user(email="owner@example.com", name="Owner")
    client = auth_client(user)

    response = client.post("/api/workspaces/", {"name": "Core", "slug": "core"}, format="json")

    assert response.status_code == 201
    workspace = Workspace.objects.get(slug="core")
    assert Member.objects.get(workspace=workspace, user=user).role == Member.ROLE_OWNER


def test_admin_invites_and_invitee_accepts():
    user_model = get_user_model()
    owner = user_model.objects.create_user(email="owner@example.com", name="Owner")
    invitee = user_model.objects.create_user(email="invitee@example.com", name="Invitee")
    workspace = Workspace.objects.create(name="Core", slug="core")
    Member.objects.create(workspace=workspace, user=owner, role=Member.ROLE_OWNER)
    owner_client = auth_client(owner)

    invite_response = owner_client.post(
        "/api/invitations/",
        {"workspace_id": str(workspace.id), "email": invitee.email, "role": Member.ROLE_MEMBER},
        format="json",
    )

    assert invite_response.status_code == 201
    invitation = Invitation.objects.get(workspace=workspace, invitee_email=invitee.email)

    invitee_client = auth_client(invitee)
    accept_response = invitee_client.post(f"/api/invitations/{invitation.id}/accept/")

    assert accept_response.status_code == 200
    assert Member.objects.filter(workspace=workspace, user=invitee, role=Member.ROLE_MEMBER).exists()
    invitation.refresh_from_db()
    assert invitation.status == Invitation.STATUS_ACCEPTED


def test_personal_access_token_create_and_revoke():
    user = get_user_model().objects.create_user(email="dev@example.com", name="Dev")
    client = auth_client(user)

    create_response = client.post("/api/tokens/", {"name": "local"}, format="json")

    assert create_response.status_code == 201
    assert create_response.data["raw"].startswith("pat_")
    token_id = create_response.data["token"]["id"]

    delete_response = client.delete(f"/api/tokens/{token_id}/")

    assert delete_response.status_code == 200
    assert PersonalAccessToken.objects.get(id=token_id).revoked is True


def test_cli_token_endpoint_issues_cli_prefixed_token():
    user = get_user_model().objects.create_user(email="cli@example.com", name="CLI")
    client = auth_client(user)

    response = client.post("/api/tokens/cli-token/", {}, format="json")

    assert response.status_code == 200
    assert response.data["token"].startswith("cli_")
    assert PersonalAccessToken.objects.get(id=response.data["id"]).token_prefix.startswith("cli_")
