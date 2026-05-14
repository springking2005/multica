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

    page.get_by_role("button", name="每日摘要", exact=True).click()
    expect(page.locator("#autopilot-dialog")).to_be_visible()
    expect(page.locator("#autopilot-title")).to_have_value("每日摘要")
    expect(page.locator("#autopilot-preview")).to_contain_text("0 9 * * *")
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)

@pytest.mark.django_db(transaction=True)
def test_autopilots_create_edit_pause_enable_delete_from_browser(page, live_server, browser_user):
    agent = create_agent(browser_user.workspace, "Autopilot CRUD Agent")

    page.goto(live_server.url + "/autopilots/")
    page.get_by_role("button", name="使用每日摘要模板").click()
    expect(page.locator("#autopilot-dialog")).to_be_visible()
    page.locator("#autopilot-title").fill("Browser CRUD Autopilot")
    page.locator("#autopilot-assignee").select_option(str(agent.id))
    page.locator("#autopilot-trigger-label").fill("Morning CRUD")
    with page.expect_response(
        lambda response: response.url.rstrip("/").endswith("/api/autopilots") and response.status in {200, 201}
    ):
        page.locator("#autopilot-save").click()
    expect(page.locator("#autopilot-list")).to_contain_text("Browser CRUD Autopilot", timeout=10_000)
    expect(page.locator("tr", has_text="Browser CRUD Autopilot")).to_contain_text("Morning CRUD", timeout=10_000)

    page.locator("tr", has_text="Browser CRUD Autopilot").get_by_role("button", name="编辑").click()
    expect(page.locator("#autopilot-dialog")).to_be_visible()
    page.locator("#autopilot-title").fill("Browser CRUD Autopilot Updated")
    page.locator("#autopilot-frequency").select_option("weekly")
    with page.expect_response(lambda response: "/api/autopilots/" in response.url and response.status == 200):
        page.locator("#autopilot-save").click()
    expect(page.locator("#autopilot-list")).to_contain_text("Browser CRUD Autopilot Updated", timeout=10_000)
    expect(page.locator("tr", has_text="Browser CRUD Autopilot Updated")).to_contain_text("0 9 * * 1", timeout=10_000)
    page.wait_for_load_state("networkidle")

    page.locator("tr", has_text="Browser CRUD Autopilot Updated").get_by_role("button", name="暂停").click()
    expect(page.locator("tr", has_text="Browser CRUD Autopilot Updated")).to_contain_text("暂停", timeout=10_000)
    page.wait_for_load_state("networkidle")
    page.locator("tr", has_text="Browser CRUD Autopilot Updated").get_by_role("button", name="启用").click()
    expect(page.locator("tr", has_text="Browser CRUD Autopilot Updated")).to_contain_text("启用", timeout=10_000)
    page.wait_for_load_state("networkidle")

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("tr", has_text="Browser CRUD Autopilot Updated").get_by_role("button", name="删除").click()
    expect(page.locator("#autopilot-list")).not_to_contain_text("Browser CRUD Autopilot Updated", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
