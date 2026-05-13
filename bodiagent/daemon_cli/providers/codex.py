"""Codex CLI provider (OpenAI)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator

try:
    from .base import Event, Provider
except ImportError:
    from base import Event, Provider  # type: ignore[no-redef]


class CodexProvider(Provider):
    @property
    def name(self) -> str:
        return "codex"

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
        # Codex uses app-server mode with JSON-RPC 2.0 over stdio
        args = [self.executable, "app-server", "--listen", "stdio://"]
        if extra_args:
            args.extend(extra_args)
        if custom_args:
            args.extend(custom_args)

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=merged_env,
        )

        # Send the prompt as a JSON-RPC notification/method call
        request_id = 0

        # Send an initialize-like message with prompt
        init_msg = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "message/send",
            "params": {
                "content": prompt,
                "role": "user",
            },
        }
        if system_prompt:
            init_msg["params"]["system"] = system_prompt
        if model:
            init_msg["params"]["model"] = model
        if resume_session_id:
            init_msg["params"]["session_id"] = resume_session_id

        if proc.stdin is not None:
            proc.stdin.write((json.dumps(init_msg) + "\n").encode())
            await proc.stdin.drain()

        try:
            async for event in _parse_codex_stream(proc):
                yield event
            await proc.wait()
        finally:
            await _terminate_process(proc)


async def _parse_codex_stream(proc: asyncio.subprocess.Process) -> AsyncIterator[Event]:
    """Parse Codex app-server JSON-RPC 2.0 output."""
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

        # JSON-RPC response or notification
        result = data.get("result", {})
        error = data.get("error")
        method = data.get("method", "")

        if error:
            yield Event(type="error", content=str(error))
            continue

        if method == "message/partial":
            text = result.get("content", result.get("delta", ""))
            if text:
                yield Event(type="text", content=text)
        elif method == "tool/use":
            yield Event(
                type="tool_use",
                tool=result.get("name", ""),
                input=result.get("arguments", {}),
                content=json.dumps(result.get("arguments", {})),
            )
        elif method == "tool/result":
            yield Event(
                type="tool_result",
                tool=result.get("tool_use_id", ""),
                output=str(result.get("content", "")),
            )
        elif method == "message/done":
            yield Event(
                type="status",
                content="completed",
                metadata={
                    "input_tokens": result.get("input_tokens", 0),
                    "output_tokens": result.get("output_tokens", 0),
                    "model": result.get("model", ""),
                },
            )
        elif "message" in data and data.get("id") is not None:
            # Direct response to a request
            msg_result = data.get("result", {})
            if isinstance(msg_result, dict) and "content" in msg_result:
                yield Event(
                    type="text",
                    content=msg_result.get("content", ""),
                    metadata={"model": msg_result.get("model", "")},
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
