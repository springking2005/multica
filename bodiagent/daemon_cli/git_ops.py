"""Git operations for daemon task execution.

Manages bare clone caches and worktree lifecycle for task workspace setup.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _run_git(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, timeout: float | None = None) -> str:
    """Run a git command and return stdout. Raises subprocess.CalledProcessError on failure."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        timeout=timeout,
    )
    result.check_returncode()
    return result.stdout.rstrip("\n")


def _repo_cache_dir(workspaces_root: Path, workspace_id: str, repo_url: str) -> Path:
    safe_name = repo_url.replace("://", "_").replace("/", "_").replace(":", "_").replace("@", "_")
    return workspaces_root / ".repos" / workspace_id / safe_name


def ensure_bare_clone(workspaces_root: Path, workspace_id: str, repo_url: str) -> Path:
    """Ensure a bare clone cache exists for the repo URL.

    Returns path to the bare repo directory.
    """
    cache_dir = _repo_cache_dir(workspaces_root, workspace_id, repo_url)
    if not cache_dir.exists():
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        _run_git(["clone", "--bare", "--filter=blob:none", repo_url, str(cache_dir)])
        logger.info("Bare clone created at %s", cache_dir)
    else:
        # Fetch latest from origin
        try:
            _run_git(["fetch", "origin"], cwd=cache_dir, timeout=30)
        except subprocess.CalledProcessError:
            logger.warning("Failed to fetch bare clone at %s", cache_dir)
    return cache_dir


def create_worktree(
    workspaces_root: Path,
    workspace_id: str,
    repo_url: str,
    branch: str,
    agent_name: str,
    task_id: str,
) -> Path:
    """Create an isolated git worktree for a task.

    Worktree path: {workspaces_root}/{workspace_id}/{repo_dir}/agent/{agent_name}/{task_id}
    Branch name: agent/{agent_name}/{task_id}
    """
    bare_path = ensure_bare_clone(workspaces_root, workspace_id, repo_url)
    repo_name = Path(repo_url).stem.replace(".git", "")
    workdir = workspaces_root / workspace_id / repo_name / "agent" / agent_name / task_id
    branch_name = f"agent/{agent_name}/{task_id}"

    workdir.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["worktree", "add", "-b", branch_name, str(workdir), branch], cwd=bare_path)

    _setup_gitignore(workdir)
    _setup_commit_hook(workdir)

    logger.info("Worktree created at %s (branch %s)", workdir, branch_name)
    return workdir


def reuse_worktree(workdir: Path, new_branch: str) -> None:
    """Reset an existing worktree and switch to a new branch.

    Performs: git reset --hard && git clean -fd && git checkout -b {new_branch}
    """
    _run_git(["reset", "--hard"], cwd=workdir)
    _run_git(["clean", "-fd"], cwd=workdir)
    _run_git(["checkout", "-b", new_branch], cwd=workdir)
    logger.info("Worktree reused at %s (branch %s)", workdir, new_branch)


def commit_and_push(workdir: Path, message: str, branch: str, co_authored_by: str | None = None) -> str:
    """Stage all changes, commit, and push to origin.

    Returns the commit hash.
    """
    _run_git(["add", "-A"], cwd=workdir)

    commit_args = ["commit", "-m", message]
    if co_authored_by:
        commit_args.extend(["-m", f"Co-authored-by: {co_authored_by}"])

    _run_git(commit_args, cwd=workdir)

    commit_hash = _run_git(["rev-parse", "HEAD"], cwd=workdir).strip()
    _run_git(["push", "origin", branch], cwd=workdir)

    logger.info("Pushed commit %s to origin/%s", commit_hash[:8], branch)
    return commit_hash


def list_branches(workdir: Path) -> list[str]:
    """List local branches in the worktree."""
    output = _run_git(["branch"], cwd=workdir)
    return [line.strip().lstrip("* ") for line in output.splitlines()]


_EXCLUDED_PATTERNS = [
    ".agent_context",
    ".claude/settings.local.json",
    ".codex/config.toml",
]


def _setup_gitignore(workdir: Path) -> None:
    """Append daemon exclusions to .gitignore if present."""
    gitignore = workdir / ".gitignore"
    existing = set()
    if gitignore.exists():
        existing = {line.strip() for line in gitignore.read_text().splitlines()}
    new_entries = [p for p in _EXCLUDED_PATTERNS if p not in existing]
    if new_entries:
        with gitignore.open("a") as f:
            for entry in new_entries:
                f.write(f"\n{entry}\n")
    # Also add to .git/info/exclude for safety
    exclude_file = workdir / ".git" / "info" / "exclude"
    exclude_file.parent.mkdir(parents=True, exist_ok=True)
    exclude_existing = set()
    if exclude_file.exists():
        exclude_existing = {line.strip() for line in exclude_file.read_text().splitlines()}
    exclude_new = [p for p in _EXCLUDED_PATTERNS if p not in exclude_existing]
    if exclude_new:
        with exclude_file.open("a") as f:
            for entry in exclude_new:
                f.write(f"\n{entry}\n")


def _setup_commit_hook(workdir: Path) -> None:
    """Install a prepare-commit-msg hook for Co-authored-by trailers."""
    hooks_dir = workdir / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hooks_dir / "prepare-commit-msg"
    if not hook_path.exists():
        script = """#!/bin/sh
# bodiagent prepare-commit-msg hook
# Adds Co-authored-by trailer from BODIAGENT_AGENT_ID env var
AGENT_ID="${BODIAGENT_AGENT_ID:-}"
if [ -n "$AGENT_ID" ]; then
    # Only add if not already present
    if ! grep -q "Co-authored-by:" "$1" 2>/dev/null; then
        echo "" >> "$1"
        echo "Co-authored-by: bodiagent-agent <$AGENT_ID@bodiagent.local>" >> "$1"
    fi
fi
"""
        hook_path.write_text(script)
        hook_path.chmod(0o755)
