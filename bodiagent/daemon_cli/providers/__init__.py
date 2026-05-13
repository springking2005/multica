"""Provider implementations: claude, openclaw, codex."""

from __future__ import annotations

try:
    from .base import Event, Provider
    from .claude import ClaudeProvider
    from .openclaw import OpenClawProvider
    from .codex import CodexProvider
    from .fake import FakeProvider
except ImportError:
    from base import Event, Provider  # type: ignore[no-redef]
    from claude import ClaudeProvider  # type: ignore[no-redef]
    from openclaw import OpenClawProvider  # type: ignore[no-redef]
    from codex import CodexProvider  # type: ignore[no-redef]
    from fake import FakeProvider  # type: ignore[no-redef]

__all__ = [
    "Event",
    "Provider",
    "ClaudeProvider",
    "OpenClawProvider",
    "CodexProvider",
    "FakeProvider",
    "detect_providers",
]


def detect_providers() -> list[Provider]:
    """Detect available AI CLI providers on the system PATH.

    Returns a list of instantiated Provider objects for each detected CLI.
    """
    import os
    import shutil

    result: list[Provider] = []
    executables: list[tuple[str, type[Provider]]] = [
        ("claude", ClaudeProvider),
        ("openclaw", OpenClawProvider),
        ("codex", CodexProvider),
    ]
    for exe, cls in executables:
        if shutil.which(exe):
            result.append(cls(exe))
    if os.environ.get("BODIAGENT_ENABLE_FAKE_PROVIDER") == "1":
        result.append(FakeProvider("fake"))
    return result


def get_provider(name: str, executable: str | None = None) -> Provider:
    """Get a provider by name, optionally with a custom executable path."""
    exe = executable or name
    if name == "claude":
        return ClaudeProvider(exe)
    if name == "openclaw":
        return OpenClawProvider(exe)
    if name == "codex":
        return CodexProvider(exe)
    if name == "fake":
        return FakeProvider(exe)
    raise ValueError(f"Unknown provider: {name}")
