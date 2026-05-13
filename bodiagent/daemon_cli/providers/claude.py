"""Claude CLI provider (Anthropic)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator

try:
    from .base import Event, Provider
except ImportError:
    from base import Event, Provider  # type: ignore[no-redef]


class ClaudeProvider(Provider):
    @property
    def name(self) -> str:
        return "claude"

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
        args = [self.executable, "-p", prompt, "--output-format", "stream-json", "--input-format", "stream-json"]
        if model:
            args.extend(["--model", model])
        if system_prompt:
            args.extend(["--system-prompt", system_prompt])
        if resume_session_id:
            args.extend(["--resume", resume_session_id])
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
            async for event in _parse_claude_stream(proc):
                yield event
            await proc.wait()
        finally:
            await _terminate_process(proc)


async def _parse_claude_stream(proc: asyncio.subprocess.Process) -> AsyncIterator[Event]:
    """Parse Claude's stream-json output line by line."""
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
        if event_type == "assistant":
            # Content block delta events
            content_blocks = data.get("content", [])
            for block in content_blocks:
                block_type = block.get("type", "")
                if block_type == "text":
                    yield Event(type="text", content=block.get("text", ""))
                elif block_type == "tool_use":
                    yield Event(
                        type="tool_use",
                        tool=block.get("name", ""),
                        input=block.get("input", {}),
                        content=json.dumps(block.get("input", {})),
                    )
                elif block_type == "tool_result":
                    yield Event(
                        type="tool_result",
                        tool=block.get("tool_use_id", ""),
                        output=str(block.get("content", "")),
                    )
        elif event_type == "error":
            yield Event(type="error", content=data.get("error", data.get("message", "unknown error")))
        elif event_type == "result":
            # Final result marker — emit usage as a status event
            usage = data.get("usage", {})
            yield Event(
                type="status",
                content="completed",
                metadata={
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
                    "cache_write_tokens": usage.get("cache_creation_input_tokens", 0),
                    "model": data.get("model", ""),
                    "duration_ms": data.get("duration_ms", 0),
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
