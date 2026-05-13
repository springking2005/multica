"""OpenClaw CLI provider."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator

try:
    from .base import Event, Provider
except ImportError:
    from base import Event, Provider  # type: ignore[no-redef]


class OpenClawProvider(Provider):
    @property
    def name(self) -> str:
        return "openclaw"

    async def execute(
        self,
        prompt: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        resume_session_id: str | None = None,
        timeout: float | None = None,
        extra_args: list[str] | None = None,
        custom_args: list[str] | None = None,
        mcp_config: dict[str, Any] | None = None,
    ) -> AsyncIterator[Event]:
        args = [self.executable, "agent", "--local", "--json", "--message", prompt]
        if model:
            args.extend(["--model", model])
        if system_prompt:
            args.extend(["--system", system_prompt])
        if resume_session_id:
            args.extend(["--session", resume_session_id])
        if extra_args:
            args.extend(extra_args)
        if custom_args:
            args.extend(custom_args)

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=merged_env,
        )

        try:
            async for event in _parse_openclaw_stream(proc):
                yield event
            await proc.wait()
        finally:
            await _terminate_process(proc)


async def _parse_openclaw_stream(proc: asyncio.subprocess.Process) -> AsyncIterator[Event]:
    """Parse OpenClaw's JSON line output."""
    if proc.stdout is None:
        return

    while True:
        line = await proc.stdout.readline()
        if not line:
            break

        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            continue

        try:
            data = json.loads(line_str)
        except json.JSONDecodeError:
            continue

        event_type = data.get("type", "")
        if event_type in ("message", "text"):
            content = data.get("content", data.get("text", ""))
            yield Event(type="text", content=content)
        elif event_type == "tool_call":
            yield Event(
                type="tool_use",
                tool=data.get("name", ""),
                input=data.get("arguments", {}),
                content=json.dumps(data.get("arguments", {})),
            )
        elif event_type == "tool_result":
            yield Event(
                type="tool_result",
                tool=data.get("tool_use_id", ""),
                output=str(data.get("content", "")),
            )
        elif event_type == "error":
            yield Event(type="error", content=data.get("error", data.get("message", "unknown error")))
        elif event_type in ("done", "complete"):
            usage = data.get("usage", {})
            yield Event(
                type="status",
                content="completed",
                metadata={
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "model": data.get("model", ""),
                },
            )


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
