"""Model creation tests for chat app."""

import uuid

import pytest
from django.contrib.auth import get_user_model

from accounts.models import Daemon, Workspace
from agents.models import Agent, Task
from chat.models import ChatMessage, ChatSession

User = get_user_model()
pytestmark = pytest.mark.django_db


class TestChatSession:
    def test_create_session(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="Hello chat",
        )
        assert session.id is not None
        assert isinstance(session.id, uuid.UUID)
        assert session.workspace == ws
        assert session.agent == agent
        assert session.creator_type == ChatSession.CREATOR_MEMBER
        assert session.creator_id == user.id
        assert session.title == "Hello chat"
        assert session.status == ChatSession.STATUS_ACTIVE
        assert session.context == {}
        assert session.created_at is not None
        assert session.updated_at is not None

    def test_create_session_with_agent_creator(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_AGENT,
            creator_id=agent.id,
            title="Agent-initiated",
        )
        assert session.creator_type == ChatSession.CREATOR_AGENT
        assert session.creator_id == agent.id

    def test_create_session_with_optional_fields(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        daemon = Daemon.objects.create(machine_id=uuid.uuid4())
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="Full session",
            session_id="resume-abc",
            work_dir="/tmp/work/abc",
            daemon=daemon,
            context={"mode": "chat"},
            unread_since=None,
        )
        assert session.session_id == "resume-abc"
        assert session.work_dir == "/tmp/work/abc"
        assert session.daemon == daemon
        assert session.context == {"mode": "chat"}
        assert session.unread_since is None

    def test_archive_session(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="To archive",
        )
        session.status = ChatSession.STATUS_ARCHIVED
        session.save()
        session.refresh_from_db()
        assert session.status == ChatSession.STATUS_ARCHIVED

    def test_str(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="My Chat",
        )
        assert str(session) == "My Chat"

    def test_str_fallback_to_id(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="",
        )
        assert str(session) == str(session.id)


class TestChatMessage:
    def test_create_user_message(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="Chat",
        )
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content="Hello, agent!",
        )
        assert msg.id is not None
        assert msg.session == session
        assert msg.role == ChatMessage.ROLE_USER
        assert msg.content == "Hello, agent!"
        assert msg.metadata == {}
        assert msg.created_at is not None

    def test_create_assistant_message(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="Chat",
        )
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content="Hi! How can I help?",
            elapsed_ms=1500,
        )
        assert msg.role == ChatMessage.ROLE_ASSISTANT
        assert msg.elapsed_ms == 1500

    def test_create_message_with_task(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="Chat",
        )
        task = Task.objects.create(agent=agent)
        msg = ChatMessage.objects.create(
            session=session,
            task=task,
            role=ChatMessage.ROLE_ASSISTANT,
            content="Working on it...",
        )
        assert msg.task == task

    def test_create_message_with_failure_reason(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="Chat",
        )
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content="Something went wrong.",
            failure_reason="Provider timeout after 30s",
            metadata={"error_code": "TIMEOUT"},
        )
        assert msg.failure_reason == "Provider timeout after 30s"
        assert msg.metadata == {"error_code": "TIMEOUT"}

    def test_create_message_with_metadata(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="Chat",
        )
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content="Analysis complete.",
            metadata={"tokens": 500, "model": "claude-sonnet-4-20250514"},
        )
        assert msg.metadata["tokens"] == 500
        assert msg.metadata["model"] == "claude-sonnet-4-20250514"

    def test_session_cascade(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="Chat",
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content="msg1",
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content="msg2",
        )
        assert ChatMessage.objects.filter(session=session).count() == 2
        session_id = session.id
        session.delete()
        assert ChatMessage.objects.filter(session_id=session_id).count() == 0

    def test_str(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Test WS", slug="test-ws")
        agent = Agent.objects.create(
            workspace=ws,
            name="Test Agent",
            provider=Agent.Provider.CLAUDE,
        )
        session = ChatSession.objects.create(
            workspace=ws,
            agent=agent,
            creator_type=ChatSession.CREATOR_MEMBER,
            creator_id=user.id,
            title="Chat",
        )
        msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            content="Hello, this is a test message.",
        )
        assert "user" in str(msg).lower()
        assert "Hello, this is a test message." in str(msg)
