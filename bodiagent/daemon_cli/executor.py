"""Task execution engine for bodiagent-daemon.

Polls for tasks, manages concurrency via asyncio.Semaphore, spawns AI CLI
subprocesses, and manages the task lifecycle: claim -> start -> progress ->
complete/fail.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from uuid import UUID

try:
    from .cleanup import mark_cancelled, mark_completed, mark_failed, mark_task_dir
    from .client import DaemonClient
    from .config import DaemonConfig
    from .git_ops import create_worktree, reuse_worktree
    from .providers import detect_providers, get_provider
except ImportError:
    from cleanup import mark_cancelled, mark_completed, mark_failed, mark_task_dir  # type: ignore[no-redef]
    from client import DaemonClient  # type: ignore[no-redef]
    from config import DaemonConfig  # type: ignore[no-redef]
    from git_ops import create_worktree, reuse_worktree  # type: ignore[no-redef]
    from providers import detect_providers, get_provider  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3.0
HEARTBEAT_FAIL_THRESHOLD = 5
CANCEL_CHECK_INTERVAL = 1.0


class TaskCancelled(RuntimeError):  # noqa: N818
    """Raised when the server marks a running task as cancelled."""


class TaskExecutor:
    """Main task execution loop.

    Polls the server for tasks per provider, manages concurrency, spawns
    subprocesses, and reports lifecycle events.
    """

    def __init__(self, config: DaemonConfig, client: DaemonClient) -> None:
        self.config = config
        self.client = client
        self._semaphore = asyncio.Semaphore(config.max_concurrent_tasks)
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._heartbeat_failures = 0

    @property
    def active_task_ids(self) -> set[str]:
        return set(self._active_tasks.keys())

    async def run(self) -> None:
        """Main execution loop. Runs until stopped."""
        self._running = True
        logger.info("Executor started (max_concurrent=%d)", self.config.max_concurrent_tasks)

        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            while self._running:
                await self._poll_and_execute()
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            heartbeat_task.cancel()
            # Wait for active tasks to finish
            if self._active_tasks:
                logger.info("Waiting for %d active tasks to finish...", len(self._active_tasks))
                await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)

    async def stop(self) -> None:
        """Signal the executor to stop."""
        self._running = False

    async def _heartbeat_loop(self) -> None:
        """Send heartbeats and handle pending server actions."""
        while self._running:
            try:
                ack = await self.client.heartbeat()
                self._heartbeat_failures = 0

                # Handle pending actions from heartbeat ack
                for key in (
                    "pending_model_list",
                    "pending_local_skills",
                    "pending_local_skill_import",
                ):
                    if ack.get(key):
                        await self._handle_pending_action(key, ack[key])
            except Exception:
                self._heartbeat_failures += 1
                if self._heartbeat_failures >= HEARTBEAT_FAIL_THRESHOLD:
                    logger.error("Heartbeat failed %d times, stopping executor", self._heartbeat_failures)
                    self._running = False
                    return
                logger.warning("Heartbeat failed (%d/%d)", self._heartbeat_failures, HEARTBEAT_FAIL_THRESHOLD)
            await asyncio.sleep(15)

    async def _poll_and_execute(self) -> None:
        """Poll for tasks and spawn execution if capacity allows."""
        try:
            task_data = await self.client.claim_task()
        except Exception:
            logger.exception("Failed to claim task")
            return

        if task_data is None:
            return  # No pending tasks

        task_id = task_data.get("id")
        if not task_id:
            return

        if task_id in self._active_tasks:
            return  # Already handling

        coro = self._execute_task_with_capacity(task_data)
        self._active_tasks[task_id] = asyncio.create_task(coro)

    async def _execute_task_with_capacity(self, task_data: dict) -> None:
        async with self._semaphore:
            await self._execute_task(task_data)

    async def _execute_task(self, task_data: dict) -> None:
        """Execute a single task through its lifecycle."""
        task_id = task_data.get("id", "")
        agent_id = task_data.get("agent_id", "")
        issue_id = task_data.get("issue_id")
        agent_name = task_data.get("agent_name", "agent")
        provider_name = task_data.get("provider", "claude")
        prompt = task_data.get("prompt", "")
        model = task_data.get("model")
        system_prompt = task_data.get("system_prompt")
        session_id = task_data.get("session_id")
        work_dir = task_data.get("work_dir")
        force_fresh = task_data.get("force_fresh_session", False)
        custom_args = task_data.get("custom_args", [])
        mcp_config = task_data.get("mcp_config")

        logger.info("Executing task %s (agent=%s, provider=%s)", task_id, agent_id, provider_name)

        try:
            # Claim: mark as started
            await self.client.task_start(UUID(task_id))
        except Exception:
            logger.exception("Failed to start task %s", task_id)
            self._active_tasks.pop(task_id, None)
            return

        # Setup workspace
        task_work_dir = await self._prepare_workspace(
            work_dir=work_dir,
            agent_name=agent_name,
            task_id=task_id,
            force_fresh=force_fresh,
        )

        # Mark GC metadata
        if task_work_dir:
            mark_task_dir(
                Path(task_work_dir),
                kind="issue" if issue_id else "chat",
                task_id=task_id,
                agent_id=agent_id,
                issue_id=issue_id,
            )

        # Get provider
        try:
            provider = get_provider(provider_name)
        except ValueError:
            provider = get_provider("claude")

        # Execute
        usage_stats: dict[str, int] = {}
        messages: list[dict] = []
        seq = 0
        completed = False
        error_msg = ""

        cancel_watch_task: asyncio.Task[None] | None = None
        try:
            env = self._build_env(task_id, agent_id)
            cancel_watch_task = asyncio.create_task(self._watch_cancel(UUID(task_id)))
            provider_events = provider.execute(
                prompt,
                cwd=task_work_dir,
                env=env,
                model=model,
                system_prompt=system_prompt,
                resume_session_id=session_id if not force_fresh else None,
                custom_args=custom_args,
                mcp_config=mcp_config,
            )

            async for event in self._iterate_until_cancelled(provider_events, cancel_watch_task):
                # Track messages for batch submit
                msg = {
                    "type": event.type,
                    "content": event.content,
                    "tool": event.tool,
                    "seq": seq,
                }
                if event.input:
                    msg["input"] = event.input
                if event.output:
                    msg["output"] = event.output
                messages.append(msg)
                seq += 1

                # Report progress periodically
                if seq % 10 == 0:
                    try:
                        await self.client.task_progress(
                            UUID(task_id),
                            step="executing",
                            message=f"Step {seq}",
                        )
                    except Exception:
                        pass

                # Collect usage from status events
                if event.type == "status" and event.metadata:
                    usage_stats = {
                        "input_tokens": event.metadata.get("input_tokens", 0),
                        "output_tokens": event.metadata.get("output_tokens", 0),
                        "cache_read_tokens": event.metadata.get("cache_read_tokens", 0),
                        "cache_write_tokens": event.metadata.get("cache_write_tokens", 0),
                    }

            completed = True
        except TaskCancelled as exc:
            error_msg = str(exc)
            logger.info("Task %s cancelled by server", task_id)
            messages.append({
                "type": "status",
                "content": error_msg,
                "seq": seq,
            })
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception("Task %s execution failed", task_id)
            messages.append({
                "type": "error",
                "content": error_msg,
                "seq": seq,
            })
        finally:
            if cancel_watch_task:
                cancel_watch_task.cancel()
            # Always sync messages
            if messages:
                try:
                    await self.client.task_messages(UUID(task_id), messages)
                except Exception:
                    logger.exception("Failed to sync messages for task %s", task_id)

        # Report final status
        try:
            if completed:
                summary = messages[-1].get("content", "") if messages else ""
                await self.client.task_complete(UUID(task_id), summary=summary)
                if task_work_dir:
                    mark_completed(Path(task_work_dir))
                logger.info("Task %s completed", task_id)
            elif error_msg == "Task cancelled by server":
                if task_work_dir:
                    mark_cancelled(Path(task_work_dir))
                logger.info("Task %s cancellation acknowledged", task_id)
            else:
                await self.client.task_fail(UUID(task_id), error=error_msg)
                if task_work_dir:
                    mark_failed(Path(task_work_dir))
                logger.info("Task %s failed: %s", task_id, error_msg)
        except Exception:
            logger.exception("Failed to report final status for task %s", task_id)

        # Submit usage
        if usage_stats:
            try:
                model_str = model or "unknown"
                await self.client.task_usage(
                    UUID(task_id),
                    provider=provider_name,
                    model=model_str,
                    **usage_stats,
                )
            except Exception:
                logger.exception("Failed to submit usage for task %s", task_id)

        self._active_tasks.pop(task_id, None)

    async def _watch_cancel(self, task_id: UUID) -> None:
        while self._running:
            await asyncio.sleep(CANCEL_CHECK_INTERVAL)
            try:
                status = await self.client.task_status(task_id)
            except Exception:
                logger.debug("Failed to poll task status for cancellation", exc_info=True)
                continue
            if status.get("status") == "cancelled":
                raise TaskCancelled("Task cancelled by server")

    async def _iterate_until_cancelled(
        self,
        events,
        cancel_watch_task: asyncio.Task[None],
    ):
        iterator = events.__aiter__()
        while True:
            next_event = asyncio.create_task(iterator.__anext__())
            done, pending = await asyncio.wait(
                {next_event, cancel_watch_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_watch_task in done:
                next_event.cancel()
                with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                    await next_event
                aclose = getattr(iterator, "aclose", None)
                if aclose:
                    with contextlib.suppress(RuntimeError):
                        await aclose()
                cancel_watch_task.result()
            try:
                yield next_event.result()
            except StopAsyncIteration:
                return
            finally:
                for task in pending:
                    if task is not cancel_watch_task:
                        task.cancel()

    async def _prepare_workspace(
        self,
        work_dir: str | None,
        agent_name: str,
        task_id: str,
        force_fresh: bool = False,
    ) -> str | None:
        """Prepare the git workspace for a task. Returns the work directory path or None."""
        if work_dir and not force_fresh:
            # Reuse existing worktree
            try:
                new_branch = f"agent/{agent_name}/{task_id}"
                reuse_worktree(Path(work_dir), new_branch)
                return work_dir
            except Exception:
                logger.warning("Failed to reuse worktree at %s, will create fresh", work_dir)

        # Create new worktree if repos are configured
        try:
            repos = await self.client.workspace_repos(UUID(self.config.workspace_id))
            if repos:
                repo = repos[0]
                repo_url = repo.get("url", "")
                branch = repo.get("default_branch", "main")
                if repo_url:
                    return str(
                        create_worktree(
                            self.config.workspaces_root,
                            self.config.workspace_id,
                            repo_url,
                            branch,
                            agent_name,
                            task_id,
                        )
                    )
        except Exception:
            logger.debug("No workspace repos configured, using temp directory")

        # Fallback to a plain directory
        fallback = self.config.workspaces_root / "tasks" / task_id
        fallback.mkdir(parents=True, exist_ok=True)
        return str(fallback)

    def _build_env(self, task_id: str, agent_id: str) -> dict[str, str]:
        """Build environment variables injected into the AI CLI subprocess."""
        return {
            "BODIAGENT_TOKEN": self.config.token,
            "BODIAGENT_SERVER_URL": self.config.server_url,
            "BODIAGENT_WORKSPACE_ID": self.config.workspace_id,
            "BODIAGENT_AGENT_ID": agent_id,
            "BODIAGENT_TASK_ID": task_id,
        }

    async def _handle_pending_action(self, action: str, data: dict) -> None:
        """Handle pending actions from the server heartbeat ack."""
        action_handlers = {
            "pending_model_list": self._report_model_list,
            "pending_local_skills": self._report_local_skills,
            "pending_local_skill_import": self._report_local_skill_import,
        }
        handler = action_handlers.get(action)
        if handler:
            try:
                await handler(data)
            except Exception:
                logger.exception("Failed to handle pending action %s", action)

    async def _report_model_list(self, data: dict) -> None:
        """Report available models from all providers."""
        request_id = data.get("id", "")
        providers = detect_providers()
        models: list[dict] = []
        for provider in providers:
            models.append({
                "id": provider.name,
                "name": provider.name,
                "provider": provider.name,
            })
        await self.client.http.post(
            f"/api/daemon/models/{request_id}/result",
            json={"request_id": request_id, "models": models},
        )

    async def _report_local_skills(self, data: dict) -> None:
        """Report local skills from providers."""
        request_id = data.get("id", "")
        skills: list[dict] = []
        await self.client.http.post(
            f"/api/daemon/local-skills/{request_id}/result",
            json={"request_id": request_id, "skills": skills},
        )

    async def _report_local_skill_import(self, data: dict) -> None:
        """Report local skill import result."""
        request_id = data.get("id", "")
        skill_key = data.get("skill_key", "")
        await self.client.http.post(
            f"/api/daemon/local-skills/import/{request_id}/result",
            json={
                "request_id": request_id,
                "skill": {
                    "name": skill_key,
                    "description": "",
                    "files": [],
                },
            },
        )
