"""Basic model creation tests for accounts models."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import (
    Daemon,
    DaemonToken,
    Invitation,
    Member,
    NotificationPreference,
    PersonalAccessToken,
    VerificationCode,
    Workspace,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


class TestUser:
    def test_create_user(self):
        user = User.objects.create_user(email="test@example.com", name="Tester")
        assert user.id is not None
        assert isinstance(user.id, uuid.UUID)
        assert user.email == "test@example.com"
        assert user.name == "Tester"
        assert user.is_active is True
        assert user.is_staff is False
        assert user.check_password("") is False

    def test_create_user_with_password(self):
        user = User.objects.create_user(email="test@example.com", password="secret123", name="Tester")
        assert user.check_password("secret123") is True

    def test_create_superuser(self):
        user = User.objects.create_superuser(email="admin@example.com", password="secret123", name="Admin")
        assert user.is_staff is True
        assert user.is_superuser is True

    def test_email_normalized(self):
        user = User.objects.create_user(email="Test@Example.COM", name="Tester")
        assert user.email == "Test@example.com".lower()

    def test_str(self):
        user = User.objects.create_user(email="test@example.com", name="Tester")
        assert str(user) == "test@example.com"


class TestWorkspace:
    def test_create_workspace(self):
        ws = Workspace.objects.create(name="Core", slug="core")
        assert ws.id is not None
        assert isinstance(ws.id, uuid.UUID)
        assert ws.slug == "core"
        assert ws.issue_counter == 0
        assert ws.repos == []
        assert ws.settings == {}
        assert ws.created_at is not None
        assert ws.updated_at is not None

    def test_slug_unique(self):
        Workspace.objects.create(name="A", slug="core")
        with pytest.raises(Exception):
            Workspace.objects.create(name="B", slug="core")

    def test_str(self):
        ws = Workspace.objects.create(name="Core", slug="core")
        assert str(ws) == "Core"


class TestMember:
    def test_create_member(self):
        user = User.objects.create_user(email="u@example.com", name="U")
        ws = Workspace.objects.create(name="Core", slug="core")
        m = Member.objects.create(workspace=ws, user=user, role=Member.ROLE_OWNER)
        assert m.role == Member.ROLE_OWNER
        assert m.workspace == ws
        assert m.user == user

    def test_unique_workspace_user(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Core", slug="core")
        Member.objects.create(workspace=ws, user=user, role=Member.ROLE_MEMBER)
        with pytest.raises(Exception):
            Member.objects.create(workspace=ws, user=user, role=Member.ROLE_ADMIN)

    def test_str(self):
        user = User.objects.create_user(email="u@example.com", name="U")
        ws = Workspace.objects.create(name="Core", slug="core")
        m = Member.objects.create(workspace=ws, user=user, role=Member.ROLE_MEMBER)
        assert "u@example.com" in str(m)
        assert "core" in str(m)


class TestInvitation:
    def test_create_invitation(self):
        inviter = User.objects.create_user(email="owner@example.com", name="Owner")
        ws = Workspace.objects.create(name="Core", slug="core")
        inv = Invitation.objects.create(
            workspace=ws,
            inviter=inviter,
            invitee_email="invitee@example.com",
            role=Member.ROLE_MEMBER,
        )
        assert inv.status == Invitation.STATUS_PENDING
        assert inv.expires_at is not None
        assert inv.expires_at > timezone.now()

    def test_expires_default(self):
        inviter = User.objects.create_user(email="o@example.com")
        ws = Workspace.objects.create(name="C", slug="c")
        inv = Invitation.objects.create(
            workspace=ws,
            inviter=inviter,
            invitee_email="i@example.com",
            role=Member.ROLE_MEMBER,
        )
        expected = inv.created_at + timedelta(days=7)
        delta = abs(inv.expires_at - expected)
        assert delta.total_seconds() < 5


class TestPersonalAccessToken:
    def test_issue_token(self):
        user = User.objects.create_user(email="dev@example.com")
        token, raw = PersonalAccessToken.issue(user, "test-token")
        assert token.id is not None
        assert raw.startswith("pat_")
        assert token.token_prefix == raw[:12]
        assert token.revoked is False
        assert token.user == user


class TestVerificationCode:
    def test_create_for_email(self):
        vc = VerificationCode.create_for_email("test@example.com")
        assert vc.email == "test@example.com"
        assert len(vc.code) == 6
        assert vc.used is False
        assert vc.attempts == 0
        assert vc.expires_at > timezone.now()

    def test_create_with_custom_code(self):
        vc = VerificationCode.create_for_email("test@example.com", code="123456")
        assert vc.code == "123456"


class TestNotificationPreference:
    def test_create_preferences(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Core", slug="core")
        prefs = NotificationPreference.objects.create(workspace=ws, user=user)
        assert prefs.assignments is True
        assert prefs.statuses is True
        assert prefs.comments is True
        assert prefs.updates is True
        assert prefs.agent_activity is True

    def test_unique_workspace_user(self):
        user = User.objects.create_user(email="u@example.com")
        ws = Workspace.objects.create(name="Core", slug="core")
        NotificationPreference.objects.create(workspace=ws, user=user)
        with pytest.raises(Exception):
            NotificationPreference.objects.create(workspace=ws, user=user)


class TestDaemon:
    def test_create_daemon(self):
        d = Daemon.objects.create(
            machine_id=uuid.uuid4(),
            device_name="test-device",
            available_providers=["claude"],
        )
        assert d.id is not None
        assert d.machine_id is not None
        assert d.device_name == "test-device"
        assert d.available_providers == ["claude"]

    def test_machine_id_unique(self):
        mid = uuid.uuid4()
        Daemon.objects.create(machine_id=mid)
        with pytest.raises(Exception):
            Daemon.objects.create(machine_id=mid)


class TestDaemonToken:
    def test_issue_token(self):
        daemon = Daemon.objects.create(machine_id=uuid.uuid4())
        token, raw = DaemonToken.issue(daemon)
        assert raw.startswith("mdt_")
        assert token.daemon == daemon
        assert token.token_hash is not None
        assert token.expires_at > timezone.now()

    def test_token_hash_unique(self):
        d1 = Daemon.objects.create(machine_id=uuid.uuid4())
        d2 = Daemon.objects.create(machine_id=uuid.uuid4())
        t1, _ = DaemonToken.issue(d1)
        t2, _ = DaemonToken.issue(d2)
        assert t1.token_hash != t2.token_hash
