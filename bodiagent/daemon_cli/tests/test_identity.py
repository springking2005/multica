"""Tests for identity module."""

import uuid
from pathlib import Path

import pytest

from daemon_cli.identity import get_machine_id, get_machine_id_path


def test_get_machine_id_returns_uuid():
    mid = get_machine_id()
    assert isinstance(mid, uuid.UUID)


def test_get_machine_id_is_stable():
    mid1 = get_machine_id()
    mid2 = get_machine_id()
    assert mid1 == mid2


def test_get_machine_id_path():
    path = get_machine_id_path()
    assert path.name == "daemon.id"
    assert ".bodiagent" in str(path)
