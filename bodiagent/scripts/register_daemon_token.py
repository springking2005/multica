#!/usr/bin/env python3
"""Legacy helper to register this machine and print an mdt_ token.

Prefer the authenticated one-step flow instead:
    bodiagent-daemon setup --server-url http://106.53.153.76:8000 --token <cli_or_pat_token> --workspace-id <uuid>

This script calls the legacy /api/daemon/register endpoint. Production servers
may disable anonymous first registration, so use this only for diagnostics or
when you already have an existing mdt_ token for the same machine_id.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

DEFAULT_SERVER_URL = "http://106.53.153.76:8000"
DEFAULT_DAEMON_DIR = Path.home() / ".bodiagent"
DEFAULT_MACHINE_ID_PATH = DEFAULT_DAEMON_DIR / "daemon.id"
DEFAULT_CONFIG_PATH = DEFAULT_DAEMON_DIR / "config.json"
KNOWN_PROVIDERS = [
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register a BodiAgent daemon and print an mdt_ token.")
    parser.add_argument("--server-url", default=os.environ.get("BODIAGENT_SERVER_URL", DEFAULT_SERVER_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("BODIAGENT_WORKSPACE_ID", ""))
    parser.add_argument(
        "--token",
        default=os.environ.get("BODIAGENT_TOKEN", ""),
        help="Existing mdt_ token for re-registering an existing machine_id.",
    )
    parser.add_argument("--device-name", default=socket.gethostname())
    parser.add_argument(
        "--provider",
        action="append",
        dest="providers",
        help="Provider to advertise. Repeatable. Default: auto-detect from PATH.",
    )
    parser.add_argument("--machine-id", default="", help="Override machine_id. Defaults to ~/.bodiagent/daemon.id.")
    parser.add_argument(
        "--write-config",
        action="store_true",
        help="Write server_url/token/workspace_id to ~/.bodiagent/config.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON only.")
    return parser.parse_args()


def load_or_create_machine_id(override: str = "") -> str:
    if override:
        return str(uuid.UUID(override))

    DEFAULT_DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    if DEFAULT_MACHINE_ID_PATH.exists():
        raw = DEFAULT_MACHINE_ID_PATH.read_text(encoding="utf-8").strip()
        if raw:
            return str(uuid.UUID(raw))

    machine_id = str(uuid.uuid4())
    DEFAULT_MACHINE_ID_PATH.write_text(machine_id, encoding="utf-8")
    return machine_id


def detect_providers(explicit: list[str] | None) -> list[str]:
    if explicit:
        return explicit
    paths = os.environ.get("PATH", "").split(os.pathsep)
    found: list[str] = []
    for provider in KNOWN_PROVIDERS:
        for directory in paths:
            candidate = Path(directory) / provider
            if candidate.exists() and os.access(candidate, os.X_OK):
                found.append(provider)
                break
    return found or ["claude"]


def post_json(url: str, payload: dict[str, Any], token: str = "") -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {url}:\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot connect to {url}: {exc}") from exc


def write_config(server_url: str, token: str, workspace_id: str) -> None:
    DEFAULT_DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if DEFAULT_CONFIG_PATH.exists():
        try:
            data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}

    data.update(
        {
            "server_url": server_url.rstrip("/"),
            "token": token,
            "workspace_id": workspace_id,
            "workspaces_root": data.get("workspaces_root", str(DEFAULT_DAEMON_DIR / "workspaces")),
            "max_concurrent_tasks": int(data.get("max_concurrent_tasks", 20)),
            "gc_interval_seconds": int(data.get("gc_interval_seconds", 3600)),
            "gc_ttl_hours": int(data.get("gc_ttl_hours", 24)),
            "gc_orphan_ttl_hours": int(data.get("gc_orphan_ttl_hours", 72)),
        }
    )
    DEFAULT_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    server_url = args.server_url.rstrip("/")
    machine_id = load_or_create_machine_id(args.machine_id)
    providers = detect_providers(args.providers)

    payload = {
        "machine_id": machine_id,
        "device_name": args.device_name,
        "providers": providers,
    }
    result = post_json(f"{server_url}/api/daemon/register", payload, args.token)
    token = str(result.get("token", ""))

    if args.write_config:
        if not args.workspace_id:
            raise SystemExit("--write-config requires --workspace-id or BODIAGENT_WORKSPACE_ID")
        if not token.startswith("mdt_"):
            raise SystemExit("server response did not include an mdt_ token; config not written")
        write_config(server_url, token, args.workspace_id)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print("Daemon registered successfully.")
    print(f"server_url: {server_url}")
    print(f"machine_id: {result.get('machine_id', machine_id)}")
    print(f"daemon_id:  {result.get('id', '')}")
    print(f"providers:  {', '.join(result.get('available_providers') or providers)}")
    print(f"token:      {token}")
    if args.write_config:
        print(f"config:     wrote {DEFAULT_CONFIG_PATH}")
    else:
        print("\nPreferred next step: use `bodiagent-daemon setup --token <cli_or_pat_token> --workspace-id <uuid>`")
        print("so the server creates/binds the daemon and writes the mdt_ runtime token automatically.")
        print("Use this script's mdt_ output only with `bodiagent-daemon setup --daemon-token ...` after binding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
