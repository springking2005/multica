"""Configuration management for bodiagent-daemon.

Loads from ~/.bodiagent/config.json (default profile) or
~/.bodiagent/profiles/{profile}/config.json. Environment variable
overrides: BODIAGENT_SERVER_URL, BODIAGENT_TOKEN, BODIAGENT_WORKSPACE_ID.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

try:
    from .identity import get_machine_id
except ImportError:
    from identity import get_machine_id

DEFAULT_CONFIG_DIR = Path.home() / ".bodiagent"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_WORKSPACES_ROOT = DEFAULT_CONFIG_DIR / "workspaces"


KNOWN_AI_CLIS = [
    "claude",
    "codex",
    "copilot",
    "openclaw",
    "opencode",
    "hermes",
    "gemini",
    "pi",
    "cursor",
    "kimi",
    "kiro",
]


@dataclass
class DaemonConfig:
    """Daemon configuration loaded from disk and overridden by env vars."""

    server_url: str = "http://localhost:8000"
    token: str = ""
    workspace_id: str = ""
    machine_id: UUID | None = None
    workspaces_root: Path = DEFAULT_WORKSPACES_ROOT
    max_concurrent_tasks: int = 20
    gc_interval_seconds: int = 3600
    gc_ttl_hours: int = 24
    gc_orphan_ttl_hours: int = 72
    available_providers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.machine_id is None:
            self.machine_id = get_machine_id()
        self.workspaces_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, profile: str | None = None) -> DaemonConfig:
        """Load configuration from disk, with env var overrides."""
        config_dir = DEFAULT_CONFIG_DIR
        if profile:
            config_file = config_dir / "profiles" / profile / "config.json"
        else:
            config_file = DEFAULT_CONFIG_FILE

        data: dict[str, object] = {}
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        return cls(
            server_url=_str_env("BODIAGENT_SERVER_URL", data.get("server_url", "http://localhost:8000")),
            token=_str_env("BODIAGENT_TOKEN", data.get("token", "")),
            workspace_id=_str_env("BODIAGENT_WORKSPACE_ID", data.get("workspace_id", "")),
            workspaces_root=Path(str(data.get("workspaces_root", DEFAULT_WORKSPACES_ROOT))),
            max_concurrent_tasks=int(data.get("max_concurrent_tasks", 20)),
            gc_interval_seconds=int(data.get("gc_interval_seconds", 3600)),
            gc_ttl_hours=int(data.get("gc_ttl_hours", 24)),
            gc_orphan_ttl_hours=int(data.get("gc_orphan_ttl_hours", 72)),
            available_providers=list(data.get("available_providers", [])) if data.get("available_providers") else [],
        )

    def save(self, profile: str | None = None) -> None:
        """Persist configuration to disk."""
        config_dir = DEFAULT_CONFIG_DIR
        if profile:
            config_dir = config_dir / "profiles" / profile
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"

        payload = {
            "server_url": self.server_url,
            "token": self.token,
            "workspace_id": self.workspace_id,
            "workspaces_root": str(self.workspaces_root),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "gc_interval_seconds": self.gc_interval_seconds,
            "gc_ttl_hours": self.gc_ttl_hours,
            "gc_orphan_ttl_hours": self.gc_orphan_ttl_hours,
            "available_providers": self.available_providers,
        }
        config_file.write_text(json.dumps(payload, indent=2))


def detect_available_clis() -> list[str]:
    """Return list of AI CLIs found on the system PATH."""
    return [name for name in KNOWN_AI_CLIS if shutil.which(name)]


def _str_env(key: str, default: object) -> str:
    val = os.environ.get(key)
    if val is not None:
        return val
    return str(default) if default else ""
