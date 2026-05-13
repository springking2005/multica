"""Provider abstract base class for AI CLI tools."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class Event:
    """A streamed event from an AI CLI subprocess."""

    type: str  # text, tool_use, tool_result, error, status
    content: str = ""
    tool: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Provider(abc.ABC):
    """Abstract base for an AI CLI provider (claude, codex, etc.).

    Subclasses must implement `execute()` which yields Event objects as the
    CLI produces output.
    """

    def __init__(self, executable: str) -> None:
        self.executable = executable

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider name (e.g. 'claude', 'codex')."""

    @abc.abstractmethod
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
        """Execute a prompt and yield streamed events."""
