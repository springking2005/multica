"""Task executor edge-case tests."""

from __future__ import annotations

import asyncio

import pytest

from daemon_cli.config import DaemonConfig
from daemon_cli.executor import TaskCancelled, TaskExecutor


class DummyClient:
    pass


async def slow_events():
    yield "first"
    await asyncio.sleep(10)
    yield "second"


@pytest.mark.asyncio
async def test_iterate_until_cancelled_does_not_aclose_running_generator():
    executor = TaskExecutor(DaemonConfig(token="t"), DummyClient())

    async def cancel_now():
        await asyncio.sleep(0.01)
        raise TaskCancelled("Task cancelled by server")

    cancel_task = asyncio.create_task(cancel_now())

    with pytest.raises(TaskCancelled):
        async for _ in executor._iterate_until_cancelled(slow_events(), cancel_task):
            pass
