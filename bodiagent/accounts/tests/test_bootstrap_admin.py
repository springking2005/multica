"""Deployment bootstrap admin command tests."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_bootstrap_admin_creates_superuser():
    call_command("bootstrap_admin", email="Admin@Example.com", password="admin123", name="admin")

    user = get_user_model().objects.get(email="admin@example.com")
    assert user.name == "admin"
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.check_password("admin123")


def test_bootstrap_admin_updates_existing_password_by_default():
    user = get_user_model().objects.create_user(email="admin@example.com", password="oldpass", name="admin")

    call_command("bootstrap_admin", email="admin@example.com", password="admin123", name="admin")

    user.refresh_from_db()
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.check_password("admin123")


def test_bootstrap_admin_can_preserve_existing_password():
    user = get_user_model().objects.create_user(email="admin@example.com", password="oldpass", name="admin")

    call_command(
        "bootstrap_admin",
        email="admin@example.com",
        password="admin123",
        name="admin",
        preserve_password=True,
    )

    user.refresh_from_db()
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.check_password("oldpass")
