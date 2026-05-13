"""Garbage collection for daemon task workspaces.

Cleans up completed/failed task directories based on TTL settings.
Reads .gc_meta.json per task directory to decide GC eligibility.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GC_META_FILE = ".gc_meta.json"

# Known heavy artifact patterns that can be cleaned early
ARTIFACT_PATTERNS = ["node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".next", "dist", "build"]


def _read_gc_meta(task_dir: Path) -> dict[str, Any] | None:
    meta_path = task_dir / GC_META_FILE
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_gc_meta(task_dir: Path, meta: dict[str, Any]) -> None:
    meta_path = task_dir / GC_META_FILE
    meta_path.write_text(json.dumps(meta, indent=2))


def mark_task_dir(task_dir: Path, kind: str, task_id: str, agent_id: str, issue_id: str | None = None) -> None:
    """Write GC metadata for a new task directory."""
    meta = {
        "kind": kind,
        "task_id": task_id,
        "agent_id": agent_id,
        "issue_id": issue_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
    }
    _write_gc_meta(task_dir, meta)


def mark_completed(task_dir: Path) -> None:
    meta = _read_gc_meta(task_dir)
    if meta:
        meta["status"] = "completed"
        meta["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_gc_meta(task_dir, meta)


def mark_failed(task_dir: Path) -> None:
    meta = _read_gc_meta(task_dir)
    if meta:
        meta["status"] = "failed"
        meta["failed_at"] = datetime.now(timezone.utc).isoformat()
        _write_gc_meta(task_dir, meta)


def mark_cancelled(task_dir: Path) -> None:
    meta = _read_gc_meta(task_dir)
    if meta:
        meta["status"] = "cancelled"
        meta["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        _write_gc_meta(task_dir, meta)


def is_eligible_for_gc(
    task_dir: Path,
    gc_ttl_hours: int = 24,
    gc_orphan_ttl_hours: int = 72,
    active_task_ids: set[str] | None = None,
) -> bool:
    """Check if a task directory is eligible for garbage collection.

    Rules by kind:
    - issue/chat/autopilot: GC when status is done/cancelled/archived and
      completed_at exceeds gc_ttl_hours.
    - quick_create: immediate GC after completion.
    - active tasks (in active_task_ids): never GC.
    """
    meta = _read_gc_meta(task_dir)
    if meta is None:
        # No metadata — treat as orphan
        created_at = datetime.fromtimestamp(task_dir.stat().st_mtime, tz=timezone.utc)
        age = datetime.now(timezone.utc) - created_at
        return age > timedelta(hours=gc_orphan_ttl_hours)

    # Protect active tasks
    if active_task_ids and meta.get("task_id") in active_task_ids:
        return False

    status = meta.get("status", "")
    kind = meta.get("kind", "")

    # quick_create is immediate once terminal
    if kind == "quick_create" and status in ("completed", "failed", "cancelled"):
        return True

    # issue tasks: GC when done/cancelled and beyond TTL
    if kind == "issue":
        if status not in ("completed", "failed", "cancelled"):
            return False
    # chat tasks: GC when archived and beyond TTL
    elif kind == "chat":
        if status != "archived" and status not in ("completed", "failed"):
            return False
    # autopilot tasks: GC when terminal and beyond TTL
    elif kind == "autopilot":
        if status not in ("completed", "failed", "cancelled", "skipped"):
            return False
    # Unknown kind, treat as active
    else:
        return False

    # Check TTL
    completed_field = {
        "completed": "completed_at",
        "failed": "failed_at",
        "cancelled": "cancelled_at",
    }.get(status)

    if completed_field:
        ts_str = meta.get(completed_field)
        if ts_str:
            try:
                terminal_time = datetime.fromisoformat(ts_str)
                age = datetime.now(timezone.utc) - terminal_time
                return age > timedelta(hours=gc_ttl_hours)
            except ValueError:
                pass

    return False


def clean_artifacts(task_dir: Path) -> int:
    """Remove heavy build artifacts (node_modules, etc.) from task dir.

    Returns number of removed directories.
    """
    removed = 0
    for pattern in ARTIFACT_PATTERNS:
        for p in task_dir.rglob(pattern):
            if p.is_dir():
                try:
                    shutil.rmtree(p)
                    removed += 1
                    logger.debug("Cleaned artifact: %s", p)
                except OSError:
                    logger.warning("Failed to remove artifact: %s", p)
    return removed


def remove_task_dir(task_dir: Path) -> bool:
    """Remove a task directory entirely. Returns True on success."""
    try:
        shutil.rmtree(task_dir)
        logger.info("GC removed: %s", task_dir)
        return True
    except OSError:
        logger.warning("GC failed to remove: %s", task_dir)
        return False


def collect_garbage(
    workspaces_root: Path,
    gc_ttl_hours: int = 24,
    gc_orphan_ttl_hours: int = 72,
    active_task_ids: set[str] | None = None,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Run garbage collection across all task directories.

    Returns (directories_removed, artifacts_cleaned).
    """
    dirs_removed = 0
    artifacts_cleaned = 0

    for task_dir in workspaces_root.rglob(GC_META_FILE):
        parent = task_dir.parent
        if is_eligible_for_gc(parent, gc_ttl_hours, gc_orphan_ttl_hours, active_task_ids):
            if not dry_run:
                if remove_task_dir(parent):
                    dirs_removed += 1
            else:
                logger.info("GC would remove: %s", parent)
                dirs_removed += 1

    # Artifact-only cleanup for active directories
    for task_dir in workspaces_root.rglob(GC_META_FILE):
        parent = task_dir.parent
        meta = _read_gc_meta(parent)
        if meta and meta.get("status") == "active":
            if not dry_run:
                artifacts_cleaned += clean_artifacts(parent)

    return dirs_removed, artifacts_cleaned
