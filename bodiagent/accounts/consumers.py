"""Stub consumers — populated as M1 accounts and M9 daemon are built."""

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class DaemonConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket endpoint for daemon connections — built in M9."""

    async def connect(self):
        await self.accept()

    async def receive_json(self, content, **kwargs):
        pass
