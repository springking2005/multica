"""Shared fixtures for integration/E2E tests."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Daemon, Member, Workspace
from agents.models import Agent
from integration.factories import (
    AgentFactory,
    DaemonFactory,
    MemberFactory,
    ProjectFactory,
    UserFactory,
    WorkspaceFactory,
)

User = get_user_model()


@pytest.fixture
def api_client(db):
    """Return an APIClient authenticated as a user with a workspace."""
    user = UserFactory(email="testuser@example.com", name="Test User")
    workspace = WorkspaceFactory(name="Test Workspace", slug="test-ws", issue_prefix="TST")
    MemberFactory(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_WORKSPACE_ID"] = str(workspace.id)
    client.test_user = user
    client.test_workspace = workspace
    return client


@pytest.fixture
def test_workspace(db):
    """Standalone workspace fixture."""
    return WorkspaceFactory(name="Test Workspace", slug="test-ws", issue_prefix="TST")


@pytest.fixture
def test_user(db):
    """Standalone user fixture."""
    return UserFactory(email="testuser@example.com", name="Test User")


@pytest.fixture
def test_daemon(db):
    """Standalone daemon fixture."""
    return DaemonFactory(device_name="test-daemon")


@pytest.fixture
def test_agent(db, test_workspace, test_daemon):
    """Agent bound to a workspace and daemon."""
    return AgentFactory(workspace=test_workspace, daemon=test_daemon, name="Test Agent")


@pytest.fixture
def test_project(db, test_workspace):
    """Project in a workspace."""
    return ProjectFactory(workspace=test_workspace, title="Test Project")
