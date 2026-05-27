"""Accounts, auth, workspace, member, invitation, daemon, and token API views."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Daemon,
    DaemonToken,
    Invitation,
    Member,
    PersonalAccessToken,
    VerificationCode,
    Workspace,
)
from .serializers import (
    AuthResponseSerializer,
    CreateInvitationSerializer,
    CreateTokenSerializer,
    DaemonBindSerializer,
    DaemonHeartbeatSerializer,
    DaemonRegisterSerializer,
    DaemonSerializer,
    DaemonSetupSerializer,
    DaemonWorkspaceBindingSerializer,
    InvitationSerializer,
    LoginSerializer,
    MemberSerializer,
    PersonalAccessTokenSerializer,
    RegisterSerializer,
    SendCodeSerializer,
    UpdateMemberSerializer,
    UpdateUserSerializer,
    UserSerializer,
    VerifyCodeSerializer,
    WorkspaceSerializer,
)
from .workspace_scope import (
    bind_daemon_to_workspace,
    require_workspace_admin,
    resolve_daemon_from_claim,
    resolve_workspace_id,
)

User = get_user_model()


def user_is_workspace_admin(user, workspace: Workspace) -> bool:
    return Member.objects.filter(
        workspace=workspace,
        user=user,
        role__in=(Member.ROLE_OWNER, Member.ROLE_ADMIN),
    ).exists()


def user_is_workspace_owner(user, workspace: Workspace) -> bool:
    return Member.objects.filter(workspace=workspace, user=user, role=Member.ROLE_OWNER).exists()


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    auth_login(request, user)
    return Response(AuthResponseSerializer.for_user(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data["user"]
    auth_login(request, user)
    return Response(AuthResponseSerializer.for_user(user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    refresh_token = request.data.get("refresh")
    if refresh_token:
        try:
            RefreshToken(refresh_token).blacklist()
        except Exception:
            pass
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def send_code(request):
    serializer = SendCodeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    code = getattr(settings, "BODIAGENT_DEV_VERIFICATION_CODE", None) or None
    VerificationCode.create_for_email(serializer.validated_data["email"], code=code)
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_code(request):
    serializer = VerifyCodeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"]
    user, _ = User.objects.get_or_create(email=email, defaults={"name": email.split("@", 1)[0]})
    return Response(AuthResponseSerializer.for_user(user))


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "GET":
        return Response(UserSerializer(request.user).data)
    serializer = UpdateUserSerializer(request.user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(UserSerializer(request.user).data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def onboarding(request):
    user = request.user
    questionnaire = dict(user.onboarding_questionnaire or {})
    step = request.data.get("step")
    data = request.data.get("data", {})
    if step:
        questionnaire[str(step)] = data
    else:
        questionnaire.update(data if isinstance(data, dict) else {})
    user.onboarding_questionnaire = questionnaire
    user.save(update_fields=["onboarding_questionnaire", "updated_at"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def onboarding_complete(request):
    request.user.onboarded_at = timezone.now()
    request.user.save(update_fields=["onboarded_at", "updated_at"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cloud_waitlist(request):
    request.user.cloud_waitlist_email = request.data.get("email") or request.user.email
    request.user.cloud_waitlist_reason = request.data.get("reason", "")
    request.user.save(update_fields=["cloud_waitlist_email", "cloud_waitlist_reason", "updated_at"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def starter_content_import(request):
    request.user.starter_content_state = "imported"
    request.user.save(update_fields=["starter_content_state", "updated_at"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def starter_content_dismiss(request):
    request.user.starter_content_state = "dismissed"
    request.user.save(update_fields=["starter_content_state", "updated_at"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cli_token(request):
    token, raw = PersonalAccessToken.issue(request.user, "CLI token", prefix="cli_")
    return Response({"token": raw, "id": str(token.id)})


class AuthViewSet(viewsets.GenericViewSet):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    @action(detail=False, methods=["post"])
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AuthResponseSerializer.for_user(user), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def login(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(AuthResponseSerializer.for_user(serializer.validated_data["user"]))

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def logout(self, request):
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except Exception:
                pass
        return Response({"ok": True})

    @action(detail=False, methods=["post"])
    def verify(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user, _ = User.objects.get_or_create(email=email, defaults={"name": email.split("@", 1)[0]})
        return Response(AuthResponseSerializer.for_user(user))

    @action(detail=False, methods=["post"], url_path="send-code")
    def send_code(self, request):
        serializer = SendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = getattr(settings, "BODIAGENT_DEV_VERIFICATION_CODE", None) or None
        VerificationCode.create_for_email(serializer.validated_data["email"], code=code)
        return Response({"ok": True})


class UserViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    @action(detail=False, methods=["get", "patch"])
    def me(self, request):
        if request.method == "GET":
            return Response(UserSerializer(request.user).data)
        serializer = UpdateUserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)

    @action(detail=False, methods=["patch"])
    def profile(self, request):
        serializer = UpdateUserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)

    @action(detail=False, methods=["patch"])
    def onboarding(self, request):
        user = request.user
        questionnaire = dict(user.onboarding_questionnaire or {})
        step = request.data.get("step")
        data = request.data.get("data", {})
        if step:
            questionnaire[str(step)] = data
        else:
            questionnaire.update(data if isinstance(data, dict) else {})
        user.onboarding_questionnaire = questionnaire
        user.save(update_fields=["onboarding_questionnaire", "updated_at"])
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="onboarding/complete")
    def onboarding_complete(self, request):
        request.user.onboarded_at = timezone.now()
        request.user.save(update_fields=["onboarded_at", "updated_at"])
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="onboarding/cloud-waitlist")
    def cloud_waitlist(self, request):
        request.user.cloud_waitlist_email = request.data.get("email") or request.user.email
        request.user.cloud_waitlist_reason = request.data.get("reason", "")
        request.user.save(update_fields=["cloud_waitlist_email", "cloud_waitlist_reason", "updated_at"])
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="starter-content/import")
    def starter_content_import(self, request):
        request.user.starter_content_state = "imported"
        request.user.save(update_fields=["starter_content_state", "updated_at"])
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="starter-content/dismiss")
    def starter_content_dismiss(self, request):
        request.user.starter_content_state = "dismissed"
        request.user.save(update_fields=["starter_content_state", "updated_at"])
        return Response({"ok": True})


class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "workspace_id"

    def get_queryset(self):
        return Workspace.objects.filter(members__user=self.request.user).distinct().order_by("created_at")

    def perform_create(self, serializer):
        workspace = serializer.save()
        Member.objects.create(workspace=workspace, user=self.request.user, role=Member.ROLE_OWNER)

    def destroy(self, request, *args, **kwargs):
        workspace = self.get_object()
        if not user_is_workspace_owner(request.user, workspace):
            return Response({"detail": "Only workspace owners may delete."}, status=status.HTTP_403_FORBIDDEN)
        workspace.delete()
        return Response({"ok": True})

    @action(detail=True, methods=["post"], url_path="leave")
    def leave(self, request, workspace_id=None):
        workspace = self.get_object()
        membership = Member.objects.get(workspace=workspace, user=request.user)
        if membership.role == Member.ROLE_OWNER:
            other_owners = Member.objects.filter(workspace=workspace, role=Member.ROLE_OWNER).exclude(id=membership.id)
            if not other_owners.exists():
                return Response({"detail": "Last owner cannot leave workspace."}, status=status.HTTP_400_BAD_REQUEST)
        membership.delete()
        return Response({"ok": True})

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, workspace_id=None):
        workspace = self.get_object()
        if request.method == "GET":
            members = Member.objects.filter(workspace=workspace).select_related("user").order_by("created_at")
            return Response(MemberSerializer(members, many=True).data)

        if not user_is_workspace_admin(request.user, workspace):
            return Response({"detail": "Admin role required."}, status=status.HTTP_403_FORBIDDEN)
        serializer = CreateInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = Invitation.objects.create(
            workspace=workspace,
            inviter=request.user,
            invitee_email=User.objects.normalize_email(serializer.validated_data["email"]).lower(),
            invitee_user=User.objects.filter(
                email=User.objects.normalize_email(serializer.validated_data["email"]).lower()
            ).first(),
            role=serializer.validated_data["role"],
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"members/(?P<member_id>[^/.]+)")
    def member_detail(self, request, workspace_id=None, member_id=None):
        workspace = self.get_object()
        if not user_is_workspace_admin(request.user, workspace):
            return Response({"detail": "Admin role required."}, status=status.HTTP_403_FORBIDDEN)
        member = get_object_or_404(Member.objects.select_related("user"), workspace=workspace, id=member_id)
        if member.role == Member.ROLE_OWNER:
            return Response({"detail": "Workspace owner cannot be modified here."}, status=status.HTTP_400_BAD_REQUEST)
        if request.method == "DELETE":
            member.delete()
            return Response({"ok": True})

        serializer = UpdateMemberSerializer(member, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MemberSerializer(member).data)


class MemberViewSet(viewsets.ModelViewSet):
    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "member_id"

    def get_queryset(self):
        workspace_id = resolve_workspace_id(self.request, required=False)
        queryset = Member.objects.filter(workspace__members__user=self.request.user).select_related("user", "workspace")
        if workspace_id is not None:
            queryset = queryset.filter(workspace_id=workspace_id)
        return queryset

    def perform_create(self, serializer):
        workspace = serializer.validated_data["workspace"]
        scoped_workspace_id = resolve_workspace_id(self.request, required=False)
        if scoped_workspace_id is not None and workspace.id != scoped_workspace_id:
            raise ValidationError({"workspace_id": "Body workspace must match resolved workspace scope."})
        if not user_is_workspace_admin(self.request.user, workspace):
            self.permission_denied(self.request, message="Admin role required.")
        serializer.save()

    def update(self, request, *args, **kwargs):
        member = self.get_object()
        if not user_is_workspace_admin(request.user, member.workspace):
            return Response({"detail": "Admin role required."}, status=status.HTTP_403_FORBIDDEN)
        if member.role == Member.ROLE_OWNER:
            return Response({"detail": "Workspace owner cannot be modified here."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = UpdateMemberSerializer(member, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MemberSerializer(member).data)

    def destroy(self, request, *args, **kwargs):
        member = self.get_object()
        if not user_is_workspace_admin(request.user, member.workspace):
            return Response({"detail": "Admin role required."}, status=status.HTTP_403_FORBIDDEN)
        if member.role == Member.ROLE_OWNER:
            return Response({"detail": "Workspace owner cannot be removed here."}, status=status.HTTP_400_BAD_REQUEST)
        member.delete()
        return Response({"ok": True})


class InvitationViewSet(viewsets.ModelViewSet):
    serializer_class = InvitationSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "invitation_id"

    def get_queryset(self):
        return Invitation.objects.filter(
            status=Invitation.STATUS_PENDING,
            invitee_email=self.request.user.email,
        ).select_related("workspace", "inviter").order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = CreateInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = get_object_or_404(
            Workspace.objects.filter(members__user=request.user),
            id=request.data.get("workspace") or request.data.get("workspace_id"),
        )
        if not user_is_workspace_admin(request.user, workspace):
            return Response({"detail": "Admin role required."}, status=status.HTTP_403_FORBIDDEN)
        invitation = Invitation.objects.create(
            workspace=workspace,
            inviter=request.user,
            invitee_email=User.objects.normalize_email(serializer.validated_data["email"]).lower(),
            invitee_user=User.objects.filter(
                email=User.objects.normalize_email(serializer.validated_data["email"]).lower()
            ).first(),
            role=serializer.validated_data["role"],
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def accept(self, request, invitation_id=None):
        invitation = self.get_object()
        Member.objects.get_or_create(
            workspace=invitation.workspace,
            user=request.user,
            defaults={"role": invitation.role},
        )
        invitation.status = Invitation.STATUS_ACCEPTED
        invitation.invitee_user = request.user
        invitation.save(update_fields=["status", "invitee_user", "updated_at"])
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def decline(self, request, invitation_id=None):
        invitation = self.get_object()
        invitation.status = Invitation.STATUS_DECLINED
        invitation.save(update_fields=["status", "updated_at"])
        return Response({"ok": True})


class DaemonRegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = DaemonRegisterSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        daemon = result["daemon"]
        return Response(
            {
                "id": str(daemon.id),
                "machine_id": str(daemon.machine_id),
                "device_name": daemon.device_name,
                "available_providers": daemon.available_providers,
                "token": result["token"],
            },
            status=status.HTTP_201_CREATED,
        )


class DaemonHeartbeatView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = DaemonHeartbeatSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        daemon = serializer.context["daemon"]
        if "available_providers" in serializer.validated_data:
            daemon.available_providers = serializer.validated_data["available_providers"]
        daemon.last_heartbeat = timezone.now()
        daemon.save(update_fields=["available_providers", "last_heartbeat", "updated_at"])
        return Response({"ok": True})


class DaemonViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DaemonSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "daemon_id"

    def get_queryset(self):
        workspace_id = resolve_workspace_id(self.request)
        return Daemon.objects.filter(
            workspace_bindings__workspace_id=workspace_id,
            workspace_bindings__revoked_at__isnull=True,
        ).distinct().order_by("-created_at")

    @action(detail=False, methods=["post"], url_path="bind")
    def bind(self, request):
        workspace_id = resolve_workspace_id(request)
        require_workspace_admin(request, workspace_id)
        serializer = DaemonBindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        daemon = resolve_daemon_from_claim(request)
        binding = bind_daemon_to_workspace(daemon, workspace_id, created_by=request.user)
        return Response(DaemonWorkspaceBindingSerializer(binding).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="setup")
    def setup(self, request):
        serializer = DaemonSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace_id = serializer.validated_data["workspace_id"]
        require_workspace_admin(request, workspace_id)
        machine_id = serializer.validated_data["machine_id"]
        defaults = {
            "device_name": serializer.validated_data.get("device_name", ""),
            "available_providers": serializer.validated_data.get("available_providers", []),
            "last_heartbeat": timezone.now(),
        }
        with transaction.atomic():
            daemon, created = Daemon.objects.select_for_update().get_or_create(
                machine_id=machine_id,
                defaults=defaults,
            )
            unauthorized_binding_exists = (
                daemon.workspace_bindings.filter(revoked_at__isnull=True)
                .exclude(
                    workspace__members__user=request.user,
                    workspace__members__role__in=(Member.ROLE_OWNER, Member.ROLE_ADMIN),
                )
                .exists()
            )
            if unauthorized_binding_exists:
                raise PermissionDenied("Existing daemon is bound to another workspace.")
            if not created:
                for field, value in defaults.items():
                    setattr(daemon, field, value)
                daemon.save(update_fields=["device_name", "available_providers", "last_heartbeat", "updated_at"])
            binding = bind_daemon_to_workspace(daemon, workspace_id, created_by=request.user)
            _token, raw = DaemonToken.issue(daemon)
        return Response(
            {
                "daemon": DaemonSerializer(daemon).data,
                "binding": DaemonWorkspaceBindingSerializer(binding).data,
                "token": raw,
            },
            status=status.HTTP_201_CREATED,
        )


class PATViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "token_id"

    def get_queryset(self):
        return PersonalAccessToken.objects.filter(user=self.request.user, revoked=False).order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return CreateTokenSerializer
        return PersonalAccessTokenSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token, raw = PersonalAccessToken.issue(
            request.user,
            serializer.validated_data["name"],
            serializer.validated_data.get("expires_at"),
        )
        return Response(
            {"token": PersonalAccessTokenSerializer(token).data, "raw": raw},
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        token = self.get_object()
        token.revoked = True
        token.save(update_fields=["revoked"])
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="cli-token")
    def cli_token(self, request):
        token, raw = PersonalAccessToken.issue(request.user, "CLI token", prefix="cli_")
        return Response({"token": raw, "id": str(token.id)})


PersonalAccessTokenViewSet = PATViewSet
