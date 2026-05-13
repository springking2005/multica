from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_agent


@pytest.mark.django_db(transaction=True)
def test_agents_page_lists_seeded_agent(page, live_server, browser_user):
    create_agent(browser_user.workspace, "Browser Agent")

    page.goto(live_server.url + "/agents/")

    expect(page.get_by_role("heading", name="智能体")).to_be_visible()
    expect(page.locator("#agent-grid")).to_contain_text("Browser Agent", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_agents_create_dialog_validation_stays_on_page(page, live_server, browser_user):
    page.goto(live_server.url + "/agents/")

    page.get_by_role("button", name="创建智能体").click()
    expect(page.locator("#agent-form")).to_be_visible()
    page.locator("textarea[name='custom_env']").fill("{")
    page.locator("#agent-form button[type='submit']").click()
    expect(page.locator("#agent-form")).to_be_visible()
    expect(page.locator("#agent-alert")).to_be_visible(timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
