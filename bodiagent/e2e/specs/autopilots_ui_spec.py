from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_agent, create_autopilot


@pytest.mark.django_db(transaction=True)
def test_autopilots_page_lists_seeded_autopilot(page, live_server, browser_user):
    agent = create_agent(browser_user.workspace, "Autopilot Agent")
    create_autopilot(browser_user.workspace, browser_user.member, agent)

    page.goto(live_server.url + "/autopilots/")

    expect(page.get_by_role("heading", name="自动驾驶")).to_be_visible()
    expect(page.locator("#autopilot-list")).to_contain_text("E2E Autopilot", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_autopilot_template_opens_prefilled_dialog(page, live_server, browser_user):
    create_agent(browser_user.workspace, "Template Agent")
    page.goto(live_server.url + "/autopilots/")

    page.get_by_role("button", name="每日摘要").click()
    expect(page.locator("#autopilot-dialog")).to_be_visible()
    expect(page.locator("#autopilot-title")).to_have_value("每日摘要")
    expect(page.locator("#autopilot-preview")).to_contain_text("每天")
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
