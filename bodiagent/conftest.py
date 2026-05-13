"""Pytest configuration — shared fixtures and settings."""

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """All tests get DB access by default."""
    pass


@pytest.fixture
def dev_verification_code():
    """Development verification code for auth tests."""
    return getattr(settings, "BODIAGENT_DEV_VERIFICATION_CODE", "888888")
