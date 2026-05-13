"""Machine identity — persistent UUID managed at ~/.bodiagent/daemon.id."""

import os
import uuid
from pathlib import Path

DEFAULT_DAEMON_DIR = Path.home() / ".bodiagent"
MACHINE_ID_FILE = "daemon.id"


def ensure_daemon_dir() -> Path:
    """Create ~/.bodiagent if it does not exist."""
    DEFAULT_DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DAEMON_DIR


def get_machine_id_path() -> Path:
    return ensure_daemon_dir() / MACHINE_ID_FILE


def _load_machine_id() -> uuid.UUID | None:
    path = get_machine_id_path()
    if not path.exists():
        return None
    raw = path.read_text().strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _save_machine_id(machine_id: uuid.UUID) -> None:
    path = get_machine_id_path()
    path.write_text(str(machine_id))


def get_machine_id() -> uuid.UUID:
    """Return the persistent machine-scoped UUID, creating it if necessary.

    The machine_id is shared across profiles and stored at
    ~/.bodiagent/daemon.id.
    """
    mid = _load_machine_id()
    if mid is None:
        mid = uuid.uuid4()
        _save_machine_id(mid)
    return mid
