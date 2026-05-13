"""Deterministic fake provider for daemon E2E harnesses."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator

try:
    from .base import Event, Provider
except ImportError:
    from base import Event, Provider  # type: ignore[no-redef]


class FakeProvider(Provider):
    """A provider that streams predictable events without external CLI credentials."""

    @property
    def name(self) -> str:
        return "fake"

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
        args = _parse_args(custom_args or [])
        trace_path = (env or {}).get("BODIAGENT_FAKE_PROVIDER_TRACE")

        try:
            yield Event(type="text", content=f"fake:start:{prompt}")
            for index in range(args["events"]):
                if args["delay"] > 0:
                    await asyncio.sleep(args["delay"])
                if args["error_after"] is not None and index >= args["error_after"]:
                    raise RuntimeError("fake provider requested failure")
                yield Event(
                    type="tool_use",
                    tool="fake.step",
                    input={"index": index, "cwd": cwd or ""},
                    content=str(index),
                )
                yield Event(
                    type="tool_result",
                    tool="fake.step",
                    output=f"ok:{index}",
                )
            yield Event(
                type="status",
                content="completed",
                metadata={
                    "input_tokens": len(prompt),
                    "output_tokens": args["events"],
                    "model": model or "fake-model",
                },
            )
        finally:
            if trace_path:
                path = Path(trace_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("closed\n")


def _parse_args(custom_args: list[str]) -> dict[str, int | float | None]:
    result: dict[str, int | float | None] = {
        "events": 2,
        "delay": 0.0,
        "error_after": None,
    }
    index = 0
    while index < len(custom_args):
        key = custom_args[index]
        value = custom_args[index + 1] if index + 1 < len(custom_args) else ""
        if key == "--fake-events":
            result["events"] = max(0, int(value))
            index += 2
        elif key == "--fake-delay":
            result["delay"] = max(0.0, float(value))
            index += 2
        elif key == "--fake-error-after":
            result["error_after"] = max(0, int(value))
            index += 2
        else:
            index += 1
    return result
