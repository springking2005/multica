from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from e2e.helpers.assertions import collect_console_errors
from e2e.helpers.data import BrowserUser, create_browser_user, force_login_context, login_context_via_api

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
django_settings.SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"


def reserve_tcp_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


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


@pytest.fixture(scope="session")
def asgi_live_server(django_db_setup, django_db_blocker) -> Iterator[SimpleNamespace]:
    """Run a real ASGI server in an isolated subprocess for WebSocket specs.

    Using an external Daphne process avoids leaking event-loop state between
    Channels communicator tests and Playwright browser tests in mixed pytest
    runs. The child process is pointed at pytest's file-backed SQLite database.
    """
    host = "127.0.0.1"
    with django_db_blocker.unblock():
        default_connection = connections["default"]
        if default_connection.vendor == "sqlite" and default_connection.is_in_memory_db():
            raise ImproperlyConfigured("ASGI browser tests require a file-backed test database.")
        db_name = str(default_connection.settings_dict["NAME"])

    port = reserve_tcp_port(host)
    env = os.environ.copy()
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "bodiagent.settings_dev",
            "DJANGO_ALLOW_ASYNC_UNSAFE": "true",
            "BODIAGENT_TEST_SQLITE_NAME": db_name,
        }
    )
    log = tempfile.TemporaryFile(mode="w+b")
    process = subprocess.Popen(
        [sys.executable, "-m", "daphne", "-b", host, "-p", str(port), "e2e.asgi:application"],
        cwd=django_settings.BASE_DIR,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"http://{host}:{port}"
    try:
        deadline = time.monotonic() + 20
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(url + "/health/", timeout=0.5) as response:
                    if response.status < 500:
                        break
            except (OSError, urllib.error.URLError) as error:
                last_error = error
                time.sleep(0.1)
        else:
            raise RuntimeError(f"Daphne server did not become ready: {last_error}")
        if process.poll() is not None:
            log.seek(0)
            output = log.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Daphne server exited before readiness with code {process.returncode}\n{output}")
        yield SimpleNamespace(url=url, ws_url=f"ws://{host}:{port}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()


@pytest.fixture
def asgi_context(browser: Browser, asgi_live_server, browser_user: BrowserUser) -> Iterator[BrowserContext]:
    context = browser.new_context(base_url=asgi_live_server.url, viewport={"width": 1280, "height": 900})
    login_context_via_api(context, asgi_live_server.url, browser_user)
    yield context
    context.close()


@pytest.fixture
def asgi_page(asgi_context: BrowserContext) -> Iterator[Page]:
    page = asgi_context.new_page()
    page.console_errors = collect_console_errors(page)  # type: ignore[attr-defined]
    yield page
    page.close()


@pytest.fixture
def browser_user(transactional_db) -> BrowserUser:
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
