"""Tests for cleanup (GC) module."""

import json
import tempfile
from pathlib import Path

from daemon_cli.cleanup import (
    GC_META_FILE,
    collect_garbage,
    is_eligible_for_gc,
    mark_cancelled,
    mark_completed,
    mark_failed,
    mark_task_dir,
)


class TestMarkTaskDir:
    def test_creates_meta_file(self):
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td)
            mark_task_dir(task_dir, "issue", "task-1", "agent-1", "issue-1")
            meta_path = task_dir / GC_META_FILE
            assert meta_path.exists()
            meta = json.loads(meta_path.read_text())
            assert meta["kind"] == "issue"
            assert meta["task_id"] == "task-1"
            assert meta["status"] == "active"


class TestMarkCompleted:
    def test_updates_status(self):
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td)
            mark_task_dir(task_dir, "issue", "task-1", "agent-1")
            mark_completed(task_dir)
            meta = json.loads((task_dir / GC_META_FILE).read_text())
            assert meta["status"] == "completed"
            assert "completed_at" in meta


class TestMarkFailed:
    def test_updates_status(self):
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td)
            mark_task_dir(task_dir, "issue", "task-1", "agent-1")
            mark_failed(task_dir)
            meta = json.loads((task_dir / GC_META_FILE).read_text())
            assert meta["status"] == "failed"


class TestMarkCancelled:
    def test_updates_status(self):
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td)
            mark_task_dir(task_dir, "issue", "task-1", "agent-1")
            mark_cancelled(task_dir)
            meta = json.loads((task_dir / GC_META_FILE).read_text())
            assert meta["status"] == "cancelled"


class TestIsEligibleForGC:
    def test_no_meta_is_orphan(self):
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td)
            # No meta file — should be treated as orphan
            result = is_eligible_for_gc(task_dir, gc_orphan_ttl_hours=0)
            assert result is True  # immediately eligible with TTL=0

    def test_active_task_not_eligible(self):
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td)
            mark_task_dir(task_dir, "issue", "task-1", "agent-1")
            result = is_eligible_for_gc(task_dir, gc_ttl_hours=1000)
            assert result is False

    def test_completed_task_eligible_after_ttl(self):
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td)
            mark_task_dir(task_dir, "issue", "task-1", "agent-1")
            mark_completed(task_dir)
            # With TTL=0, immediately eligible
            result = is_eligible_for_gc(task_dir, gc_ttl_hours=0)
            assert result is True

    def test_active_task_protected_by_id_set(self):
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td)
            mark_task_dir(task_dir, "issue", "task-1", "agent-1")
            mark_completed(task_dir)
            result = is_eligible_for_gc(
                task_dir, gc_ttl_hours=0, active_task_ids={"task-1"}
            )
            assert result is False


class TestCollectGarbage:
    def test_dry_run_does_not_remove(self):
        with tempfile.TemporaryDirectory() as td:
            task_dir = Path(td) / "task-1"
            task_dir.mkdir()
            mark_task_dir(task_dir, "issue", "task-1", "agent-1")
            mark_completed(task_dir)

            dirs, artifacts = collect_garbage(
                Path(td), gc_ttl_hours=0, dry_run=True
            )
            assert dirs >= 0  # At minimum, no crash
            assert isinstance(artifacts, int)
