"""DRF serializers for accounts and workspace APIs."""

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import models
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
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


class UserSerializer(serializers.ModelSerializer):
    onboarding_completed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "name",
            "avatar_url",
            "onboarding_completed",
            "onboarded_at",
            "onboarding_questionnaire",
            "language",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "onboarding_completed")

    def get_onboarding_completed(self, obj):
        return obj.onboarded_at is not None


class UpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("name", "avatar_url", "language")


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def create(self, validated_data):
        email = User.objects.normalize_email(validated_data["email"]).lower()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"name": validated_data.get("name") or email.split("@", 1)[0]},
        )
        if created and validated_data.get("password"):
            user.set_password(validated_data["password"])
            user.save(update_fields=["password", "updated_at"])
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=User.objects.normalize_email(attrs["email"]).lower(),
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("Invalid email or password")
        attrs["user"] = user
        return attrs


class SendCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField()

    def validate(self, attrs):
        email = User.objects.normalize_email(attrs["email"]).lower()
        code = attrs["code"]
        dev_code = getattr(settings, "BODIAGENT_DEV_VERIFICATION_CODE", None)
        if dev_code and code == dev_code:
            attrs["email"] = email
            return attrs

        verification = (
            VerificationCode.objects.filter(email=email, code=code, used=False, expires_at__gt=timezone.now())
            .order_by("-created_at")
            .first()
        )
        if verification is None:
            VerificationCode.objects.filter(email=email, used=False).update(attempts=models.F("attempts") + 1)
            raise serializers.ValidationError("Invalid verification code")
        verification.used = True
        verification.save(update_fields=["used"])
        attrs["email"] = email
        return attrs


class AuthResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()

    @classmethod
    def for_user(cls, user):
        refresh = RefreshToken.for_user(user)
        return {
            "token": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        }


class WorkspaceSerializer(serializers.ModelSerializer):
    icon = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Workspace
        fields = (
            "id",
            "name",
            "slug",
            "icon",
            "description",
            "settings",
            "context",
            "repos",
            "issue_prefix",
            "issue_counter",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "issue_counter", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data.pop("icon", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("icon", None)
        return super().update(instance, validated_data)


class MemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        source="user",
        queryset=User.objects.all(),
        write_only=True,
        required=False,
    )
    workspace_id = serializers.PrimaryKeyRelatedField(
        source="workspace",
        queryset=Workspace.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Member
        fields = ("id", "user", "user_id", "workspace", "workspace_id", "role", "created_at")
        read_only_fields = ("id", "user", "workspace", "created_at")


class UpdateMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ("role",)

    def validate_role(self, value):
        if value == Member.ROLE_OWNER:
            raise serializers.ValidationError("Owner role cannot be assigned here")
        return value


class InvitationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="invitee_email", read_only=True)
    workspace_name = serializers.CharField(source="workspace.name", read_only=True)

    class Meta:
        model = Invitation
        fields = (
            "id",
            "workspace",
            "workspace_name",
            "email",
            "inviter",
            "role",
            "expires_at",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "workspace",
            "workspace_name",
            "inviter",
            "created_at",
            "updated_at",
        )


class CreateInvitationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=(Member.ROLE_ADMIN, Member.ROLE_MEMBER), default=Member.ROLE_MEMBER)


class PersonalAccessTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalAccessToken
        fields = (
            "id",
            "user",
            "name",
            "token_hash",
            "token_prefix",
            "revoked",
            "last_used_at",
            "expires_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "user",
            "name",
            "token_hash",
            "token_prefix",
            "revoked",
            "last_used_at",
            "expires_at",
            "created_at",
        )


class CreateTokenSerializer(serializers.Serializer):
    name = serializers.CharField()
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class CreateTokenResponseSerializer(serializers.Serializer):
    token = PersonalAccessTokenSerializer()
    raw = serializers.CharField()


class VerificationCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationCode
        fields = ("id", "email", "code", "attempts", "used", "expires_at", "created_at")
        read_only_fields = ("id", "attempts", "used", "created_at")
        extra_kwargs = {"code": {"write_only": True}}


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = (
            "id",
            "workspace",
            "user",
            "assignments",
            "statuses",
            "comments",
            "updates",
            "agent_activity",
            "updated_at",
        )
        read_only_fields = ("id", "updated_at")


class DaemonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Daemon
        fields = (
            "id",
            "machine_id",
            "device_name",
            "available_providers",
            "device_info",
            "metadata",
            "last_heartbeat",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "last_heartbeat", "created_at", "updated_at")


class DaemonRegisterSerializer(serializers.Serializer):
    machine_id = serializers.UUIDField()
    device_name = serializers.CharField(required=False, allow_blank=True, default="")
    providers = serializers.ListField(
        child=serializers.CharField(), required=False, default=list, source="available_providers"
    )

    def create(self, validated_data):
        machine_id = validated_data["machine_id"]
        daemon, _ = Daemon.objects.update_or_create(
            machine_id=machine_id,
            defaults={
                "device_name": validated_data.get("device_name", ""),
                "available_providers": validated_data.get("available_providers", []),
                "last_heartbeat": timezone.now(),
                "updated_at": timezone.now(),
            },
        )
        token, raw = DaemonToken.issue(daemon)
        return {"daemon": daemon, "token": raw}


class DaemonHeartbeatSerializer(serializers.Serializer):
    machine_id = serializers.UUIDField()

    def validate_machine_id(self, value):
        try:
            daemon = Daemon.objects.get(machine_id=value)
        except Daemon.DoesNotExist:
            raise serializers.ValidationError("Unknown machine_id")
        self.context["daemon"] = daemon
        return value


class DaemonTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DaemonToken
        fields = ("id", "daemon", "token_hash", "expires_at", "created_at")
        read_only_fields = ("id", "token_hash", "created_at")
        extra_kwargs = {"token_hash": {"write_only": True}}
