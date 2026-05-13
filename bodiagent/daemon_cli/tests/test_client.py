"""Daemon client HTTP contract tests."""

from __future__ import annotations

import uuid

import httpx
import pytest

from daemon_cli.client import DaemonClient


@pytest.mark.asyncio
async def test_claim_task_returns_none_for_empty_queue_404():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "No pending tasks for this daemon."})

    client = DaemonClient("http://server.test", "token", uuid.uuid4())
    client.daemon_id = str(uuid.uuid4())
    client._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://server.test",
    )

    try:
        assert await client.claim_task() is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_progress_and_messages_match_server_schema():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = DaemonClient("http://server.test", "token", uuid.uuid4())
    client._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://server.test",
    )
    task_id = uuid.uuid4()

    try:
        await client.task_progress(task_id, step="executing", message="Step 10", percent=50)
        await client.task_messages(task_id, [{"kind": "text", "content": "hello", "seq": 1}])
    finally:
        await client.close()

    assert requests[0].url.path.endswith(f"/api/daemon/tasks/{task_id}/progress")
    assert requests[0].content == (
        b'{"type":"status","content":"Step 10","metadata":{"step":"executing","percent":50}}'
    )
    assert requests[1].url.path.endswith(f"/api/daemon/tasks/{task_id}/messages")
    assert requests[1].content == b'{"messages":[{"content":"hello","seq":1,"type":"text"}]}'
