"""Chat frontend shell tests."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Member, Workspace
from agents.models import Agent
from chat.models import ChatSession

User = get_user_model()
pytestmark = pytest.mark.django_db


def create_chat_session():
    user = User.objects.create_user(email="chat-ui@example.com", password="pw")
    workspace = Workspace.objects.create(name="Chat UI WS", slug="chat-ui-ws")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    agent = Agent.objects.create(
        workspace=workspace,
        name="Chat Agent",
        provider=Agent.Provider.CLAUDE,
    )
    session = ChatSession.objects.create(
        workspace=workspace,
        agent=agent,
        creator_type=ChatSession.CREATOR_MEMBER,
        creator_id=user.id,
        title="UI session",
    )
    return user, workspace, session


def test_chat_page_requires_login(client):
    response = client.get(reverse("chat-new"))

    assert response.status_code == 302
    assert "/login/" in response["Location"]


def test_chat_page_renders_session_context(client):
    user, workspace, session = create_chat_session()
    client.force_login(user)

    response = client.get(reverse("chat-detail", kwargs={"session_id": session.id}))

    assert response.status_code == 200
    assert response.context["session_id"] == str(session.id)
    assert response.context["current_workspace_id"] == str(workspace.id)
    content = response.content.decode()
    assert 'id="chat-app"' in content
    assert f'data-session-id="{session.id}"' in content
    assert f'data-workspace-id="{workspace.id}"' in content
    assert "textContent = message.content" in content
