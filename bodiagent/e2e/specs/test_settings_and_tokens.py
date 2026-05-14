from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_cli_token


@pytest.mark.django_db(transaction=True)
def test_tokens_page_lists_existing_token(page, live_server, browser_user):
    create_cli_token(browser_user.user, "Browser CLI Token")

    page.goto(live_server.url + "/settings/tokens/")

    expect(page.get_by_role("heading", name="CLI Token", exact=True)).to_be_visible()
    expect(page.locator("#token-list")).to_contain_text("Browser CLI Token", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)

@pytest.mark.django_db(transaction=True)
def test_token_create_reveals_one_time_value(page, live_server, browser_user):
    page.goto(live_server.url + "/settings/tokens/")

    page.locator("#token-name").fill("Browser Generated Token")
    with page.expect_response(lambda response: response.url.endswith("/api/tokens/") and response.status == 201):
        page.locator("#token-submit").click()
    expect(page.locator("#token-raw")).to_be_visible(timeout=10_000)
    expect(page.locator("#token-raw-code")).not_to_be_empty()
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)

@pytest.mark.django_db(transaction=True)
def test_token_validation_and_revoke_from_browser(page, live_server, browser_user):
    create_cli_token(browser_user.user, "Browser Revoked Token")

    page.goto(live_server.url + "/settings/tokens/")
    expect(page.locator("#token-list")).to_contain_text("Browser Revoked Token", timeout=10_000)

    page.locator("#token-name").fill("")
    page.locator("#token-submit").click()
    expect(page.locator("#token-alert")).to_contain_text("请填写 Token 名称", timeout=10_000)

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#token-list").get_by_role("button", name="撤销").click()
    expect(page.locator("#token-list")).not_to_contain_text("Browser Revoked Token", timeout=10_000)
    expect(page.locator("#token-alert")).to_contain_text("Token 已撤销", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_profile_update_saves_without_raw_json(page, live_server, browser_user):
    page.goto(live_server.url + "/settings/")

    expect(page.get_by_role("heading", name="个人设置")).to_be_visible()
    expect(page.locator("#profile-email")).to_have_value(browser_user.user.email)
    expect(page.locator("#profile-email")).to_have_attribute("readonly", "")

    page.locator("#profile-name").fill("Browser Profile Name")
    page.locator("#profile-avatar-url").fill("https://example.com/avatar.png")
    page.locator("#profile-language").select_option("en")
    with page.expect_response(lambda response: response.url.endswith("/api/me") and response.status == 200):
        page.locator("#profile-submit").click()

    expect(page.locator("#profile-msg")).to_contain_text("个人信息已保存", timeout=10_000)
    page.reload()
    expect(page.locator("#profile-name")).to_have_value("Browser Profile Name", timeout=10_000)
    expect(page.locator("#profile-avatar-url")).to_have_value("https://example.com/avatar.png")
    expect(page.locator("#profile-language")).to_have_value("en")
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_profile_validation_theme_and_readonly_notifications(page, live_server, browser_user):
    page.goto(live_server.url + "/settings/")

    page.locator("#profile-name").fill("")
    page.locator("#profile-submit").click()
    expect(page.locator("#profile-msg")).to_contain_text("请填写姓名", timeout=10_000)

    page.get_by_role("button", name="深色").click()
    expect(page.get_by_role("button", name="深色")).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("() => localStorage.getItem('theme')") == "dark"

    expect(page.locator("#notification-readonly-note")).to_contain_text("尚未接入")
    expect(page.locator("input[aria-disabled='true']")).to_have_count(5)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
