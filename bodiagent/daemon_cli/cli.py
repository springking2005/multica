"""Click CLI entry point for bodiagent-daemon.

Commands: start, stop, status, restart, setup, update, config, version.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import socket
import sys
from pathlib import Path
from typing import Any

import click

try:
    from .cleanup import collect_garbage
    from .client import DaemonClient
    from .config import DaemonConfig, detect_available_clis
    from .executor import TaskExecutor
except ImportError:
    from cleanup import collect_garbage
    from client import DaemonClient
    from config import DaemonConfig, detect_available_clis
    from executor import TaskExecutor


@click.group()
@click.version_option(version="0.1.0", prog_name="bodiagent-daemon")
def main() -> None:
    """波笛智能体 Daemon CLI — local task execution agent."""


@main.command()
@click.option("--foreground", is_flag=True, help="Run in foreground (do not daemonize).")
@click.option("--profile", default=None, help="Configuration profile name.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
def start(foreground: bool, profile: str | None, verbose: bool) -> None:
    """Start the daemon process."""
    _setup_logging(verbose)

    config = DaemonConfig.load(profile)
    clis = detect_available_clis()
    config.available_providers = clis
    config.save(profile)

    if not config.token:
        click.echo("Error: No token configured. Run 'bodiagent-daemon setup' first.", err=True)
        sys.exit(1)

    click.echo(f"Starting bodiagent-daemon (server={config.server_url})")
    click.echo(f"Machine ID: {config.machine_id}")
    click.echo(f"Available providers: {', '.join(clis) if clis else 'none'}")

    client = DaemonClient(
        server_url=config.server_url,
        token=config.token,
        machine_id=config.machine_id,
    )
    executor = TaskExecutor(config, client)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run() -> None:
        # Register with server
        import socket
        device_name = socket.gethostname()
        try:
            result = await client.register(device_name, clis)
            click.echo(f"Registered: {json.dumps(result, indent=2)}")
        except Exception:
            click.echo("Warning: Failed to register with server (continuing anyway)")

        # Start WebSocket connection in background
        ws_task = asyncio.create_task(client.connect_ws())

        # Start executor
        try:
            await executor.run()
        except asyncio.CancelledError:
            pass
        finally:
            ws_task.cancel()

    # Handle shutdown signals
    async def _shutdown(sig: signal.Signals) -> None:
        click.echo(f"\nReceived signal {sig.name}, shutting down...")
        await executor.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.ensure_future(_shutdown(s)),
        )

    try:
        loop.run_until_complete(_run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(client.close())
        loop.close()
        click.echo("Daemon stopped.")


@main.command()
def stop() -> None:
    """Stop a running daemon process."""
    pid_file = Path.home() / ".bodiagent" / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            click.echo(f"Sent SIGTERM to daemon (PID {pid})")
        except (ValueError, ProcessLookupError):
            click.echo("Daemon is not running.")
        except PermissionError:
            click.echo("Permission denied: cannot stop daemon.", err=True)
            sys.exit(1)
    else:
        click.echo("No PID file found. Daemon may not be running.")


@main.command()
@click.option("--profile", default=None, help="Configuration profile name.")
def status(profile: str | None) -> None:
    """Show daemon status."""
    config = DaemonConfig.load(profile)
    click.echo("Configuration:")
    click.echo(f"  Server URL:     {config.server_url}")
    click.echo(f"  Token:          {'***' if config.token else '(not set)'}")
    click.echo(f"  Workspace ID:   {config.workspace_id or '(not set)'}")
    click.echo(f"  Machine ID:     {config.machine_id}")
    click.echo(f"  Max concurrent: {config.max_concurrent_tasks}")
    click.echo(f"  Workspaces:     {config.workspaces_root}")
    click.echo(f"  GC TTL:         {config.gc_ttl_hours}h")

    clis = detect_available_clis()
    click.echo(f"\nDetected AI CLIs: {', '.join(clis) if clis else 'none'}")

    pid_file = Path.home() / ".bodiagent" / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            click.echo(f"\nDaemon PID: {pid}")
        except ValueError:
            click.echo("\nDaemon: not running (stale PID file)")
    else:
        click.echo("\nDaemon: not running")


@main.command()
@click.option("--profile", default=None, help="Configuration profile name.")
def restart(profile: str | None) -> None:
    """Restart the daemon."""
    ctx = click.get_current_context()
    ctx.invoke(stop)
    ctx.invoke(start, foreground=True, profile=profile)


@main.command()
@click.option("--server-url", default=None, help="BodiAgent server URL.")
@click.option("--user-token", "user_token", default=None, help="User JWT/PAT/CLI token for setup.")
@click.option("--token", "user_token_alias", default=None, help="Alias for --user-token.")
@click.option("--workspace-id", default=None, help="Workspace UUID to bind this daemon to.")
@click.option("--daemon-token", default=None, help="Existing daemon token (mdt_...) to save without user setup.")
@click.option("--profile", default=None, help="Configuration profile name.")
def setup(
    server_url: str | None,
    user_token: str | None,
    user_token_alias: str | None,
    workspace_id: str | None,
    daemon_token: str | None,
    profile: str | None,
) -> None:
    """Configure, register, and bind this machine as a workspace daemon."""
    click.echo("bodiagent-daemon setup")
    click.echo("=" * 40)

    server_url = server_url or click.prompt("Server URL", default="http://localhost:8000")
    clis = detect_available_clis()
    click.echo(f"Detected AI CLIs: {', '.join(clis) if clis else 'none'}")

    if daemon_token:
        workspace_id = workspace_id or click.prompt("Workspace ID (UUID)")
        config = DaemonConfig(server_url=server_url, token=daemon_token, workspace_id=workspace_id)
        config.save(profile)
        click.echo("Saved existing daemon token. The daemon must already be bound to this workspace.")
        return

    user_token = user_token or user_token_alias or click.prompt(
        "User token (JWT, pat_..., or cli_...)", hide_input=True
    )

    bootstrap_config = DaemonConfig(server_url=server_url, token="", workspace_id=workspace_id or "")
    client = DaemonClient(server_url=server_url, token="", machine_id=bootstrap_config.machine_id)

    async def _setup() -> dict[str, Any]:
        nonlocal workspace_id
        if not workspace_id:
            workspaces = await client.list_workspaces(user_token)
            if not workspaces:
                raise click.ClickException("No workspaces are available for this user token.")
            if len(workspaces) == 1:
                workspace_id = str(workspaces[0]["id"])
                click.echo(f"Using workspace: {workspaces[0].get('name', workspace_id)} ({workspace_id})")
            else:
                click.echo("Available workspaces:")
                for item in workspaces:
                    click.echo(f"  {item.get('id')}  {item.get('name', '')}")
                workspace_id = click.prompt("Workspace ID (UUID)")
        return await client.setup_daemon(user_token, workspace_id, socket.gethostname(), clis)

    async def _setup_with_close() -> dict[str, Any]:
        try:
            return await _setup()
        finally:
            await client.close()

    try:
        result = asyncio.run(_setup_with_close())
    except Exception as exc:
        message = _format_setup_error(exc, user_token)
        raise click.ClickException(message) from exc

    raw_daemon_token = result.get("token")
    if not raw_daemon_token:
        raise click.ClickException("Server did not return a daemon token.")
    config = DaemonConfig(server_url=server_url, token=raw_daemon_token, workspace_id=workspace_id or "")
    config.available_providers = clis
    config.save(profile)
    daemon_id = (result.get("daemon") or {}).get("id", "")
    click.echo("\nSetup complete.")
    click.echo("Configuration saved to ~/.bodiagent/config.json")
    click.echo(f"Daemon ID: {daemon_id or '(unknown)'}")
    click.echo(f"Machine ID: {config.machine_id}")
    click.echo(f"Workspace ID: {config.workspace_id}")
    click.echo("Token saved: mdt_... (daemon runtime token)")


@main.command()
@click.argument("action", type=click.Choice(["check", "run", "clean-artifacts"]))
@click.option("--dry-run", is_flag=True, help="Preview what would be removed.")
@click.option("--ttl", type=int, default=None, help="Override GC TTL in hours.")
@click.option("--profile", default=None, help="Configuration profile name.")
def update(action: str, dry_run: bool, ttl: int | None, profile: str | None) -> None:
    """Self-update from release server.

    ACTION: 'check' for available updates, 'run' to apply update.
    """
    config = DaemonConfig.load(profile)

    if action == "check":
        click.echo(f"Checking for updates from {config.server_url}")
        click.echo("Update check not yet implemented.")
    elif action == "run":
        click.echo("Self-update not yet implemented.")
    elif action == "clean-artifacts":
        gc_ttl = ttl or config.gc_ttl_hours
        dirs_removed, artifacts_cleaned = collect_garbage(
            config.workspaces_root,
            gc_ttl_hours=gc_ttl,
            gc_orphan_ttl_hours=config.gc_orphan_ttl_hours,
            dry_run=dry_run,
        )
        if dry_run:
            click.echo(f"Would remove {dirs_removed} expired task dirs, {artifacts_cleaned} artifacts.")
        else:
            click.echo(f"Removed {dirs_removed} expired task dirs, cleaned {artifacts_cleaned} artifacts.")


@main.command()
@click.option("--get", multiple=True, help="Config keys to show.")
@click.option("--set", "set_flag", is_flag=True, help="Set config value (use with --key and --value).")
@click.option("--key", default=None, help="Config key to set.")
@click.option("--value", default=None, help="Config value to set.")
@click.option("--profile", default=None, help="Configuration profile name.")
def config(get: tuple[str, ...], set_flag: bool, key: str | None, value: str | None, profile: str | None) -> None:
    """View or modify configuration."""
    cfg = DaemonConfig.load(profile)

    if set_flag and key:
        field_map = {
            "server_url": "server_url",
            "token": "token",
            "workspace_id": "workspace_id",
            "max_concurrent_tasks": "max_concurrent_tasks",
            "gc_ttl_hours": "gc_ttl_hours",
            "gc_orphan_ttl_hours": "gc_orphan_ttl_hours",
        }
        if key not in field_map:
            click.echo(f"Unknown config key: {key}", err=True)
            click.echo(f"Valid keys: {', '.join(field_map)}")
            sys.exit(1)

        attr = field_map[key]
        field_type = type(getattr(cfg, attr))
        if field_type is int:
            setattr(cfg, attr, int(value or 0))
        else:
            setattr(cfg, attr, value)

        cfg.save(profile)
        click.echo(f"Set {key} = {getattr(cfg, attr)}")
    else:
        keys_to_show = list(get) if get else [
            "server_url", "token", "workspace_id", "max_concurrent_tasks",
            "gc_ttl_hours", "gc_orphan_ttl_hours",
        ]
        for k in keys_to_show:
            val = getattr(cfg, k, None)
            if k == "token" and val:
                val = val[:12] + "..." if len(val) > 15 else "***"
            click.echo(f"{k}: {val}")


@main.command()
@click.option("--profile", default=None, help="Configuration profile name.")
def version(profile: str | None) -> None:
    """Show version information."""
    config = DaemonConfig.load(profile)
    click.echo("bodiagent-daemon v0.1.0")
    click.echo(f"Machine ID: {config.machine_id}")
    clis = detect_available_clis()
    click.echo(f"Detected AI CLIs: {', '.join(clis) if clis else 'none'}")


def _format_setup_error(exc: Exception, user_token: str) -> str:
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        prefix = user_token[:4]
        hint = ""
        if status in (401, 403) and prefix == "mdt_":
            hint = " Setup requires a user token (JWT, pat_..., or cli_...), not an mdt_ daemon token."
        elif status in (401, 403) and prefix == "cli_":
            hint = " The server must include CLI/PAT authentication support for cli_ tokens."
        elif status == 403:
            hint = " Confirm the token user is an owner/admin of the workspace."
        return f"Server returned HTTP {status}: {detail}.{hint}"
    return str(exc)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


if __name__ == "__main__":
    main()
