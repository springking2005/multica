from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_htmx_loaded, assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_issue


@pytest.mark.django_db(transaction=True)
def test_issues_board_renders_api_cards(page, live_server, browser_user):
    create_issue(browser_user.workspace, browser_user.member, title="Browser board issue", status="backlog", priority="high")

    page.goto(live_server.url + "/issues/")
    assert_htmx_loaded(page)
    expect(page.get_by_role("heading", name="Issue 看板")).to_be_visible()
    expect(page.locator(".issue-card", has_text="Browser board issue")).to_be_visible(timeout=10_000)

    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_issues_board_mobile_smoke(page, live_server, browser_user):
    create_issue(browser_user.workspace, browser_user.member, title="Mobile board issue", status="todo")
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(live_server.url + "/issues/")

    expect(page.get_by_role("heading", name="Issue 看板")).to_be_visible()
    expect(page.locator(".kanban-column").first).to_be_visible()
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
