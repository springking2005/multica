"""WebSocket consumer for real-time chat."""

from uuid import UUID

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from accounts.models import Member
from chat.models import ChatMessage, ChatSession


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """Bidirectional WebSocket for chat:{session_id} group messages.

    Supports agent streaming responses via WebSocket.
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or user.is_anonymous:
            await self.close(code=4001)
            return

        self.session_id = self.scope.get("url_route", {}).get("kwargs", {}).get("session_id")
        if not self.session_id:
            await self.close(code=4002)
            return
        try:
            UUID(str(self.session_id))
        except ValueError:
            await self.close(code=4002)
            return

        self.session = await self._get_authorized_session(self.session_id, user.id)
        if self.session is None:
            await self.close(code=4003)
            return

        self.group_name = f"chat_{self.session_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Handle incoming messages from the client."""
        msg_type = content.get("type", "message")

        if msg_type == "message":
            text = str(content.get("content", "")).strip()
            if not text:
                return
            message = await self._create_message(text)
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.message",
                    "payload": {
                        "id": str(message.id),
                        "session_id": str(self.session_id),
                        "role": "user",
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                    },
                },
            )
        elif msg_type == "ping":
            await self.send_json({"type": "pong"})

    async def chat_message(self, event):
        """Handler for chat.message events from the group."""
        await self.send_json(event["payload"])

    async def chat_done(self, event):
        """Handler for chat.done events (agent response finished)."""
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _get_authorized_session(self, session_id, user_id):
        session = (
            ChatSession.objects.select_related("workspace")
            .filter(id=session_id, status=ChatSession.STATUS_ACTIVE)
            .first()
        )
        if session is None:
            return None
        if not Member.objects.filter(workspace=session.workspace, user_id=user_id).exists():
            return None
        return session

    @database_sync_to_async
    def _create_message(self, content):
        return ChatMessage.objects.create(
            session_id=self.session_id,
            role=ChatMessage.ROLE_USER,
            content=content,
        )
