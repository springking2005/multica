"""Accounts, workspace membership, and auth-token models."""

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def default_invitation_expiry():
    return timezone.now() + timedelta(days=7)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        name = extra_fields.pop("name", "") or email.split("@", 1)[0]
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self.create_user(email, password, **extra_fields)


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    email = models.EmailField(unique=True)
    avatar_url = models.TextField(blank=True, null=True)
    onboarded_at = models.DateTimeField(blank=True, null=True)
    onboarding_questionnaire = models.JSONField(default=dict, blank=True)
    cloud_waitlist_email = models.EmailField(blank=True, null=True)
    cloud_waitlist_reason = models.TextField(blank=True, null=True)
    starter_content_state = models.CharField(max_length=32, blank=True, null=True)
    language = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "user"

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = User.objects.normalize_email(self.email).lower()
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class Workspace(TimeStampedModel):
    name = models.TextField()
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True, null=True)
    settings = models.JSONField(default=dict, blank=True)
    context = models.TextField(blank=True, null=True)
    repos = models.JSONField(default=list, blank=True)
    issue_prefix = models.TextField(default="", blank=True)
    issue_counter = models.IntegerField(default=0)

    class Meta:
        db_table = "workspace"

    def __str__(self) -> str:
        return self.name


class Member(models.Model):
    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_MEMBER = "member"
    ROLE_CHOICES = (
        (ROLE_OWNER, "Owner"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_MEMBER, "Member"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "member"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="member_workspace_user_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.workspace.slug}"


class Invitation(TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_EXPIRED, "Expired"),
    )

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invitations")
    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_invitations")
    invitee_email = models.EmailField()
    invitee_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="received_invitations",
    )
    role = models.CharField(max_length=16, choices=((Member.ROLE_ADMIN, "Admin"), (Member.ROLE_MEMBER, "Member")))
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    expires_at = models.DateTimeField(default=default_invitation_expiry)

    class Meta:
        db_table = "workspace_invitation"
        indexes = [
            models.Index(fields=["invitee_email"], name="idx_invitation_invitee_email"),
            models.Index(fields=["invitee_user"], name="idx_invitation_invitee_user"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "invitee_email"],
                condition=models.Q(status="pending"),
                name="idx_invitation_unique_pending",
            ),
        ]


class PersonalAccessToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="personal_access_tokens")
    name = models.TextField()
    token_hash = models.TextField(unique=True)
    token_prefix = models.TextField()
    expires_at = models.DateTimeField(blank=True, null=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "personal_access_token"
        indexes = [models.Index(fields=["user", "revoked"], name="idx_pat_user")]

    @classmethod
    def issue(cls, user: User, name: str, expires_at=None, prefix: str = "pat_"):
        raw = f"{prefix}{secrets.token_urlsafe(32)}"
        token = cls.objects.create(
            user=user,
            name=name,
            token_hash=hash_token(raw),
            token_prefix=raw[:12],
            expires_at=expires_at,
        )
        return token, raw


class VerificationCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    code = models.TextField()
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "verification_code"

    @classmethod
    def create_for_email(cls, email: str, code: str | None = None):
        return cls.objects.create(
            email=User.objects.normalize_email(email).lower(),
            code=code or f"{secrets.randbelow(1_000_000):06d}",
            expires_at=timezone.now() + timedelta(minutes=10),
        )


class NotificationPreference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="notification_preferences")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notification_preferences")
    assignments = models.BooleanField(default=True)
    statuses = models.BooleanField(default=True)
    comments = models.BooleanField(default=True)
    updates = models.BooleanField(default=True)
    agent_activity = models.BooleanField(default=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notification_preference"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="notification_preference_workspace_user_unique"),
        ]

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class Daemon(TimeStampedModel):
    machine_id = models.UUIDField(unique=True)
    device_name = models.TextField(default="", blank=True)
    available_providers = models.JSONField(default=list, blank=True)
    device_info = models.TextField(default="", blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_heartbeat = models.DateTimeField(db_column="last_heartbeat_at", blank=True, null=True)

    class Meta:
        db_table = "daemon"




class DaemonWorkspaceBinding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    daemon = models.ForeignKey(Daemon, on_delete=models.CASCADE, related_name="workspace_bindings")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="daemon_bindings")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_daemon_bindings",
    )
    revoked_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "daemon_workspace_binding"
        constraints = [
            models.UniqueConstraint(fields=["daemon", "workspace"], name="daemon_workspace_binding_unique"),
        ]
        indexes = [
            models.Index(fields=["workspace", "revoked_at"], name="idx_daemon_binding_ws"),
            models.Index(fields=["daemon", "revoked_at"], name="idx_daemon_binding_daemon"),
        ]

    def __str__(self) -> str:
        return f"{self.daemon_id} @ {self.workspace_id}"


class DaemonToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_hash = models.TextField(unique=True)
    daemon = models.ForeignKey(Daemon, on_delete=models.CASCADE, related_name="tokens")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "daemon_token"
        indexes = [models.Index(fields=["daemon"], name="idx_daemon_token_daemon")]

    @classmethod
    def issue(cls, daemon: Daemon, expires_at=None):
        raw = f"mdt_{secrets.token_urlsafe(32)}"
        token = cls.objects.create(
            daemon=daemon,
            token_hash=hash_token(raw),
            expires_at=expires_at or timezone.now() + timedelta(days=365),
        )
        return token, raw
