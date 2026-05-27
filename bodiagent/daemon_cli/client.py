"""WebSocket + HTTP API client for daemon-server communication."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_HEARTBEAT_INTERVAL = 15.0
MAX_BACKOFF = 60.0


@dataclass
class TaskInfo:
    task_id: UUID
    agent_id: UUID
    issue_id: UUID | None
    chat_session_id: UUID | None
    status: str
    prompt: str
    model: str | None
    system_prompt: str | None
    session_id: str | None
    work_dir: str | None
    context: dict[str, Any] | None


class DaemonClient:
    """HTTP + WebSocket client for the bodiagent daemon control plane."""

    def __init__(
        self,
        server_url: str,
        token: str,
        machine_id: UUID,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.machine_id = machine_id
        self.timeout = timeout
        self._http: httpx.AsyncClient | None = None
        self._ws: Any = None
        self._ws_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._pending_actions: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._connected = False
        self.daemon_id: str | None = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=self.timeout,
                trust_env=False,
            )
        return self._http

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def auth_headers_for(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # HTTP endpoints
    # ------------------------------------------------------------------

    async def register(self, device_name: str, providers: list[str]) -> dict[str, Any]:
        """POST /api/daemon/register"""
        resp = await self.http.post(
            "/api/daemon/register",
            json={
                "machine_id": str(self.machine_id),
                "device_name": device_name,
                "providers": providers,
            },
            headers=self._auth_headers() if self.token else None,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("id"):
            self.daemon_id = str(data["id"])
        return data


    async def list_workspaces(self, user_token: str) -> list[dict[str, Any]]:
        """GET /api/workspaces/ using a user JWT/PAT/CLI token."""
        resp = await self.http.get("/api/workspaces/", headers=self.auth_headers_for(user_token))
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "results" in data:
            return list(data["results"] or [])
        return list(data or [])

    async def setup_daemon(
        self,
        user_token: str,
        workspace_id: str,
        device_name: str,
        providers: list[str],
    ) -> dict[str, Any]:
        """POST /api/daemons/setup with user auth; returns daemon token."""
        resp = await self.http.post(
            "/api/daemons/setup/",
            json={
                "workspace_id": workspace_id,
                "machine_id": str(self.machine_id),
                "device_name": device_name,
                "providers": providers,
            },
            headers=self.auth_headers_for(user_token),
        )
        resp.raise_for_status()
        data = resp.json()
        daemon = data.get("daemon") or {}
        if daemon.get("id"):
            self.daemon_id = str(daemon["id"])
        return data

    async def bind_daemon(self, user_token: str, workspace_id: str, daemon_token: str) -> dict[str, Any]:
        """POST /api/daemons/bind with user auth and daemon token in body."""
        resp = await self.http.post(
            "/api/daemons/bind/",
            json={"daemon_token": daemon_token},
            headers={
                **self.auth_headers_for(user_token),
                "X-Daemon-Token": daemon_token,
                "X-Workspace-ID": workspace_id,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def deregister(self) -> None:
        """POST /api/daemon/deregister"""
        resp = await self.http.post("/api/daemon/deregister", headers=self._auth_headers())
        resp.raise_for_status()

    async def heartbeat(self) -> dict[str, Any]:
        """POST /api/daemon/heartbeat"""
        resp = await self.http.post(
            "/api/daemon/heartbeat",
            json={"machine_id": str(self.machine_id)},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def claim_task(self) -> dict[str, Any] | None:
        """POST /api/daemon/tasks/claim — claim next queued task."""
        if not self.daemon_id:
            raise RuntimeError("daemon_id is unknown; register daemon before claiming tasks")
        resp = await self.http.post(
            "/api/daemon/tasks/claim",
            json={"daemon_id": self.daemon_id},
            headers=self._auth_headers(),
        )
        if resp.status_code in (204, 404):
            return None
        resp.raise_for_status()
        return resp.json()

    async def list_pending_tasks(self) -> list[dict[str, Any]]:
        """GET /api/daemon/tasks/pending"""
        resp = await self.http.get("/api/daemon/tasks/pending", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def task_start(self, task_id: UUID) -> None:
        """POST /api/daemon/tasks/{task_id}/start"""
        resp = await self.http.post(f"/api/daemon/tasks/{task_id}/start", headers=self._auth_headers())
        resp.raise_for_status()

    async def task_progress(self, task_id: UUID, step: str, message: str, percent: float | None = None) -> None:
        """POST /api/daemon/tasks/{task_id}/progress"""
        payload: dict[str, Any] = {
            "type": "status",
            "content": message,
            "metadata": {"step": step},
        }
        if percent is not None:
            payload["metadata"]["percent"] = percent
        resp = await self.http.post(f"/api/daemon/tasks/{task_id}/progress", json=payload, headers=self._auth_headers())
        resp.raise_for_status()

    async def task_complete(
        self,
        task_id: UUID,
        summary: str = "",
        artifacts: list[dict[str, Any]] | None = None,
    ) -> None:
        """POST /api/daemon/tasks/{task_id}/complete"""
        resp = await self.http.post(
            f"/api/daemon/tasks/{task_id}/complete",
            json={"result": {"summary": summary, "artifacts": artifacts or []}},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()

    async def task_fail(self, task_id: UUID, error: str, detail: str = "") -> None:
        """POST /api/daemon/tasks/{task_id}/fail"""
        resp = await self.http.post(
            f"/api/daemon/tasks/{task_id}/fail",
            json={"failure_reason": f"{error}\n{detail}".strip()},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()

    async def task_usage(
        self,
        task_id: UUID,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        """POST /api/daemon/tasks/{task_id}/usage"""
        resp = await self.http.post(
            f"/api/daemon/tasks/{task_id}/usage",
            json={
                "task_id": str(task_id),
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
            },
            headers=self._auth_headers(),
        )
        resp.raise_for_status()

    async def task_status(self, task_id: UUID) -> dict[str, Any]:
        """GET /api/daemon/tasks/{task_id}/status"""
        resp = await self.http.get(f"/api/daemon/tasks/{task_id}/status", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def task_messages(self, task_id: UUID, messages: list[dict[str, Any]]) -> None:
        """POST /api/daemon/tasks/{task_id}/messages"""
        normalized = []
        for message in messages:
            item = dict(message)
            if "kind" in item and "type" not in item:
                item["type"] = item.pop("kind")
            normalized.append(item)
        resp = await self.http.post(
            f"/api/daemon/tasks/{task_id}/messages",
            json={"messages": normalized},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()

    async def get_task_messages(self, task_id: UUID) -> list[dict[str, Any]]:
        """GET /api/daemon/tasks/{task_id}/messages"""
        resp = await self.http.get(f"/api/daemon/tasks/{task_id}/messages", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def task_session(self, task_id: UUID, session_id: str) -> None:
        """POST /api/daemon/tasks/{task_id}/session"""
        resp = await self.http.post(
            f"/api/daemon/tasks/{task_id}/session",
            json={"session_id": session_id},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()

    async def workspace_repos(self, workspace_id: UUID) -> list[dict[str, Any]]:
        """GET /api/daemon/workspaces/{workspace_id}/repos"""
        resp = await self.http.get(f"/api/daemon/workspaces/{workspace_id}/repos", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def gc_check_issue(self, issue_id: UUID) -> dict[str, Any]:
        """GET /api/daemon/issues/{issue_id}/gc-check"""
        resp = await self.http.get(f"/api/daemon/issues/{issue_id}/gc-check", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def gc_check_chat(self, session_id: UUID) -> dict[str, Any]:
        """GET /api/daemon/chat-sessions/{session_id}/gc-check"""
        resp = await self.http.get(f"/api/daemon/chat-sessions/{session_id}/gc-check", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def gc_check_autopilot(self, run_id: UUID) -> dict[str, Any]:
        """GET /api/daemon/autopilot-runs/{run_id}/gc-check"""
        resp = await self.http.get(f"/api/daemon/autopilot-runs/{run_id}/gc-check", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def gc_check_task(self, task_id: UUID) -> dict[str, Any]:
        """GET /api/daemon/tasks/{task_id}/gc-check"""
        resp = await self.http.get(f"/api/daemon/tasks/{task_id}/gc-check", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def recover_orphans(self) -> dict[str, Any]:
        """POST /api/daemon/recover-orphans"""
        resp = await self.http.post("/api/daemon/recover-orphans", json={}, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # WebSocket connection
    # ------------------------------------------------------------------

    async def connect_ws(self) -> None:
        """Connect to the daemon WebSocket endpoint."""
        import websockets

        ws_url = self.server_url.replace("http://", "ws://").replace("https://", "wss://") + "/api/daemon/ws"

        backoff = 1.0
        while True:
            try:
                async for ws in websockets.connect(
                    ws_url,
                    extra_headers=self._auth_headers(),
                    ping_interval=30,
                    ping_timeout=10,
                ):
                    self._ws = ws
                    self._connected = True
                    logger.info("WebSocket connected to %s", ws_url)
                    backoff = 1.0

                    # Start heartbeat loop
                    self._heartbeat_task = asyncio.create_task(self._send_heartbeats())
                    # Listen for messages
                    await self._listen_ws()
            except (websockets.ConnectionClosed, OSError) as exc:
                self._connected = False
                logger.warning("WebSocket disconnected: %s. Reconnecting in %.1fs", exc, backoff)
            except Exception:
                self._connected = False
                logger.exception("WebSocket error, reconnecting in %.1fs", backoff)

            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                self._heartbeat_task = None

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

    async def _send_heartbeats(self) -> None:
        """Periodically send daemon heartbeat frames over WebSocket."""
        while self._connected and self._ws is not None:
            try:
                msg = json.dumps({
                    "type": "daemon:heartbeat",
                    "payload": {
                        "daemon_id": str(self.machine_id),
                    },
                })
                await self._ws.send(msg)
            except Exception:
                break
            await asyncio.sleep(DEFAULT_HEARTBEAT_INTERVAL)

    async def _listen_ws(self) -> None:
        """Listen for messages on the WebSocket and dispatch pending actions."""
        while self._ws is not None:
            try:
                raw = await self._ws.recv()
                data = json.loads(raw)
                event_type = data.get("type", "")
                payload = data.get("payload", {})

                if event_type == "daemon:heartbeat_ack":
                    # Process pending actions from server
                    for key in (
                        "pending_update",
                        "pending_model_list",
                        "pending_local_skills",
                        "pending_local_skill_import",
                    ):
                        if key in payload and payload[key] is not None:
                            await self._pending_actions.put({"action": key, "data": payload[key]})
                elif event_type == "daemon:task_available":
                    await self._pending_actions.put({"action": "task_available", "data": payload})
            except Exception:
                break

    async def disconnect(self) -> None:
        """Disconnect WebSocket and clean up."""
        self._connected = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._ws_task:
            self._ws_task.cancel()
            self._ws_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def close(self) -> None:
        await self.disconnect()
