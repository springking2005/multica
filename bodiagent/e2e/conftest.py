from __future__ import annotations

import os

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
from collections.abc import Iterator

import pytest
from django.conf import settings as django_settings
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from e2e.helpers.assertions import collect_console_errors
from e2e.helpers.data import BrowserUser, create_browser_user, force_login_context


@pytest.fixture(scope="session", autouse=True)
def signed_cookie_sessions():
    """Avoid DB-backed session contention between Playwright and live_server threads."""
    django_settings.SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"


@pytest.fixture(scope="session")
def browser_type_name() -> str:
    return os.environ.get("BODIAGENT_E2E_BROWSER", "chromium")


@pytest.fixture(scope="session")
def browser(browser_type_name: str) -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_type_name)
        browser = browser_type.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def browser_user(db) -> BrowserUser:
    return create_browser_user()


@pytest.fixture
def context(browser: Browser, live_server, browser_user: BrowserUser) -> Iterator[BrowserContext]:
    context = browser.new_context(base_url=live_server.url, viewport={"width": 1280, "height": 900})
    force_login_context(context, live_server.url, browser_user.user, browser_user.workspace)
    yield context
    context.close()


@pytest.fixture
def page(context: BrowserContext) -> Iterator[Page]:
    page = context.new_page()
    page.console_errors = collect_console_errors(page)  # type: ignore[attr-defined]
    yield page
    page.close()
