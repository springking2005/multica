from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_agent, create_issue, create_project


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("path,marker", [
    ("/issues/", "Issue 看板"),
    ("/agents/", "智能体"),
    ("/projects/", "项目"),
    ("/autopilots/", "自动驾驶"),
    ("/chat/", "智能体聊天"),
    ("/settings/tokens/", "CLI Token"),
])
def test_p0_routes_mobile_smoke(page, live_server, browser_user, path, marker):
    create_agent(browser_user.workspace, "Responsive Agent")
    create_issue(browser_user.workspace, browser_user.member, title="Responsive Issue")
    create_project(browser_user.workspace, "Responsive Project")
    page.set_viewport_size({"width": 375, "height": 812})

    page.goto(live_server.url + path)

    expect(page.get_by_text(marker).first).to_be_visible(timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "path,button_name,dialog_selector",
    [
        ("/issues/", "新建 Issue", "#issue-create-dialog"),
        ("/agents/", "创建智能体", "#agent-dialog"),
        ("/projects/", "新建项目", "#project-dialog"),
        ("/autopilots/", "新建自动驾驶", "#autopilot-dialog"),
    ],
)
def test_mobile_primary_actions_open_dialogs(page, live_server, browser_user, path, button_name, dialog_selector):
    create_agent(browser_user.workspace, "Responsive Dialog Agent")
    create_issue(browser_user.workspace, browser_user.member, title="Responsive Dialog Issue")
    create_project(browser_user.workspace, "Responsive Dialog Project")
    page.set_viewport_size({"width": 375, "height": 812})

    page.goto(live_server.url + path)

    button = page.get_by_role("button", name=button_name).first
    expect(button).to_be_visible(timeout=10_000)
    button.click()
    expect(page.locator(dialog_selector)).to_be_visible(timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_mobile_settings_actions_are_reachable(page, live_server, browser_user):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(live_server.url + "/settings/")

    expect(page.locator("#profile-submit")).to_be_visible(timeout=10_000)
    expect(page.get_by_role("button", name="深色")).to_be_visible()
    page.get_by_role("button", name="深色").click()
    expect(page.get_by_role("button", name="深色")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#notification-readonly-note")).to_be_visible()
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_mobile_token_create_controls_are_reachable(page, live_server, browser_user):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(live_server.url + "/settings/tokens/")

    expect(page.locator("#token-name")).to_be_visible(timeout=10_000)
    expect(page.locator("#token-submit")).to_be_visible()
    page.locator("#token-name").fill("Mobile Token")
    with page.expect_response(lambda response: response.url.endswith("/api/tokens/") and response.status == 201):
        page.locator("#token-submit").click()
    expect(page.locator("#token-raw")).to_be_visible(timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
