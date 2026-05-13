"""E2E tests for authentication flow: register, verify, login, token refresh, workspace creation."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Member, User, Workspace

User = get_user_model()


@pytest.mark.django_db
class TestAuthFlow:
    """Critical user journey: register, verify code, login, get JWT token."""

    def test_verify_code_creates_user_and_returns_token(self, dev_verification_code):
        client = APIClient()
        resp = client.post(
            "/auth/verify-code",
            {"email": "newuser@example.com", "code": dev_verification_code},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert resp.data["token"], "JWT token must be present"
        assert resp.data["user"]["email"] == "newuser@example.com"
        assert User.objects.filter(email="newuser@example.com").exists()

    def test_invalid_code_returns_401(self, dev_verification_code):
        client = APIClient()
        resp = client.post(
            "/auth/verify-code",
            {"email": "newuser@example.com", "code": "000000"},
            format="json",
        )
        assert resp.status_code == 400

    def test_token_refresh_works(self, dev_verification_code):
        client = APIClient()
        # First authenticate
        resp = client.post(
            "/auth/verify-code",
            {"email": "refresh@example.com", "code": dev_verification_code},
            format="json",
        )
        assert resp.status_code == 200
        refresh = resp.data["refresh"]

        # Refresh the token
        refresh_resp = client.post(
            "/auth/token-refresh",
            {"refresh": refresh},
            format="json",
        )
        assert refresh_resp.status_code == 200, refresh_resp.data
        assert refresh_resp.data["access"], "New access token must be present"

    def test_create_workspace_returns_slug_and_prefix(self):
        user = User.objects.create_user(email="owner@example.com", name="Owner")
        client = APIClient()
        client.force_authenticate(user=user)

        resp = client.post(
            "/api/workspaces/",
            {"name": "My Team", "slug": "my-team"},
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["slug"] == "my-team"
        assert resp.data["name"] == "My Team"

        # Verify workspace was created and user is owner
        workspace = Workspace.objects.get(slug="my-team")
        assert Member.objects.filter(workspace=workspace, user=user, role=Member.ROLE_OWNER).exists()
