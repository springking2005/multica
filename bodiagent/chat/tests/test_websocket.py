"""WebSocket smoke tests for chat sessions."""

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from accounts.models import Member, Workspace
from agents.models import Agent
from bodiagent.asgi import application
from chat.models import ChatMessage, ChatSession

User = get_user_model()
pytestmark = pytest.mark.django_db(transaction=True)


@database_sync_to_async
def create_chat_session(email="u@example.com"):
    user = User.objects.create_user(email=email)
    workspace = Workspace.objects.create(name="Test WS", slug=f"test-ws-{User.objects.count()}")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    agent = Agent.objects.create(
        workspace=workspace,
        name="Test Agent",
        provider=Agent.Provider.CLAUDE,
    )
    session = ChatSession.objects.create(
        workspace=workspace,
        agent=agent,
        creator_type=ChatSession.CREATOR_MEMBER,
        creator_id=user.id,
        title="Hello chat",
    )
    return user, workspace, agent, session


@database_sync_to_async
def message_exists(session, content):
    return ChatMessage.objects.filter(session=session, content=content).exists()


async def connect(path, user):
    communicator = WebsocketCommunicator(application, path)
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    return communicator, connected


@pytest.mark.asyncio
async def test_authenticated_workspace_member_can_connect():
    user, _, _, session = await create_chat_session()

    communicator, connected = await connect(f"/ws/chat/{session.id}/", user)

    assert connected is True
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_two_clients_receive_broadcast_and_message_is_persisted():
    user, _, _, session = await create_chat_session()
    first, first_connected = await connect(f"/ws/chat/{session.id}/", user)
    second, second_connected = await connect(f"/ws/chat/{session.id}/", user)

    assert first_connected is True
    assert second_connected is True

    await first.send_json_to({"type": "message", "content": "Hello agent"})

    first_payload = await first.receive_json_from()
    second_payload = await second.receive_json_from()

    assert first_payload["session_id"] == str(session.id)
    assert first_payload["role"] == "user"
    assert first_payload["content"] == "Hello agent"
    assert second_payload["content"] == "Hello agent"
    assert await message_exists(session, "Hello agent") is True

    await first.disconnect()
    await second.disconnect()


@pytest.mark.asyncio
async def test_anonymous_user_is_rejected():
    _, _, _, session = await create_chat_session()

    communicator = WebsocketCommunicator(application, f"/ws/chat/{session.id}/")
    connected, _ = await communicator.connect()

    assert connected is False


@pytest.mark.asyncio
async def test_non_member_is_rejected():
    _, _, _, session = await create_chat_session()
    outsider = await database_sync_to_async(User.objects.create_user)(email="outsider@example.com")

    communicator, connected = await connect(f"/ws/chat/{session.id}/", outsider)

    assert connected is False
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_invalid_uuid_route_is_rejected():
    user, _, _, _ = await create_chat_session()

    communicator, connected = await connect("/ws/chat/not-a-uuid/", user)

    assert connected is False
    await communicator.disconnect()
