"""Browser assertions shared by P0 Playwright specs."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from playwright.sync_api import Page, expect


def assert_htmx_loaded(page: Page) -> None:
    """Assert the global HTMX object is available on template pages."""
    expect(page.locator("script[src*='htmx']")).to_have_count(1)
    page.wait_for_function("() => Boolean(window.htmx)")


def assert_no_raw_json_page(page: Page) -> None:
    """Guard against replacing a browser page with a raw JSON API payload."""
    body = page.locator("body")
    text = body.inner_text(timeout=5_000).strip()
    assert text, "page body should not be empty"
    looks_like_json = (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]"))
    if looks_like_json:
        try:
            json.loads(text)
        except json.JSONDecodeError:
            return
        raise AssertionError(f"page body appears to be raw JSON: {text[:200]}")


def assert_no_console_errors(errors: list[str], allow: Iterable[str | Iterable[str]] = ()) -> None:
    """Fail on browser console errors, with explicit per-test allowances.

    Each allow entry may be a string that must appear in an error, or an
    iterable of strings that must all appear in the same error.
    """
    unexpected: list[str] = []
    for error in errors:
        allowed = False
        for rule in allow:
            if isinstance(rule, str):
                allowed = rule in error
            else:
                allowed = all(part in error for part in rule)
            if allowed:
                break
        if not allowed:
            unexpected.append(error)
    assert not unexpected, "browser console errors:\n" + "\n".join(unexpected)


def collect_console_errors(page: Page) -> list[str]:
    errors: list[str] = []

    def on_console(message: Any) -> None:
        if message.type == "error":
            errors.append(message.text)

    def on_page_error(error: Any) -> None:
        errors.append(str(error))

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    return errors
