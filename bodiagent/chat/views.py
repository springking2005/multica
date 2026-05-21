"""Chat session and message API views."""

from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.workspace_scope import resolve_workspace_id

from .models import ChatMessage, ChatSession
from .serializers import (
    ChatMessageSerializer,
    ChatSessionSerializer,
    CreateChatSessionSerializer,
    SendMessageSerializer,
)


class ChatSessionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ChatSessionSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "session_id"

    def get_workspace_id(self):
        return resolve_workspace_id(self.request)

    def get_queryset(self):
        return ChatSession.objects.filter(
            workspace_id=self.get_workspace_id(),
        ).order_by("-updated_at")

    def get_serializer_class(self):
        if self.action == "create":
            return CreateChatSessionSerializer
        return ChatSessionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        return Response(
            ChatSessionSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="pending-task")
    def pending_task(self, request, session_id=None):
        """Return the pending task for this chat session, if any."""
        session = self.get_object()
        from agents.models import Task

        pending = Task.objects.filter(
            agent=session.agent,
            status__in=(Task.Status.QUEUED, Task.Status.DISPATCHED, Task.Status.RUNNING),
        ).order_by("-created_at").first()
        if pending is None:
            return Response(None, status=status.HTTP_200_OK)
        return Response(
            {
                "id": str(pending.id),
                "agent_id": str(pending.agent_id),
                "status": pending.status,
                "created_at": pending.created_at,
            }
        )

    @action(detail=False, methods=["get"], url_path="pending-tasks")
    def pending_tasks(self, request):
        """List pending chat tasks across the workspace."""
        from agents.models import Task

        pending = Task.objects.filter(
            agent__workspace_id=self.get_workspace_id(),
            status__in=(Task.Status.QUEUED, Task.Status.DISPATCHED, Task.Status.RUNNING),
        ).order_by("-created_at")[:50]
        return Response(
            [
                {
                    "id": str(t.id),
                    "agent_id": str(t.agent_id),
                    "status": t.status,
                    "created_at": t.created_at,
                }
                for t in pending
            ]
        )


class ChatMessageViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "message_id"

    def get_workspace_id(self):
        return resolve_workspace_id(self.request)

    def get_queryset(self):
        session_id = self.kwargs.get("session_id")
        return ChatMessage.objects.filter(
            session_id=session_id,
            session__workspace_id=self.get_workspace_id(),
        ).order_by("created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return SendMessageSerializer
        return ChatMessageSerializer

    def create(self, request, session_id=None):
        session = get_object_or_404(
            ChatSession.objects.filter(workspace_id=self.get_workspace_id()),
            id=session_id,
        )
        serializer = self.get_serializer(
            data=request.data,
            context={"session": session, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        return Response(
            ChatMessageSerializer(message).data,
            status=status.HTTP_201_CREATED,
        )
