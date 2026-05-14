"""Pytest configuration — shared fixtures and settings."""

import os
from pathlib import Path

import pytest
from django.conf import settings

if settings.DATABASES["default"].get("ENGINE") == "django.db.backends.sqlite3":
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
    test_db = Path(settings.BASE_DIR) / f"test_e2e_{worker_id}.sqlite3"
    settings.DATABASES["default"].setdefault("TEST", {})["NAME"] = str(test_db)


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """All tests get DB access by default."""
    pass


@pytest.fixture
def dev_verification_code():
    """Development verification code for auth tests."""
    return getattr(settings, "BODIAGENT_DEV_VERIFICATION_CODE", "888888")
