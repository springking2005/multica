from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_cli_token


@pytest.mark.django_db(transaction=True)
def test_tokens_page_lists_existing_token(page, live_server, browser_user):
    create_cli_token(browser_user.user, "Browser CLI Token")

    page.goto(live_server.url + "/settings/tokens/")

    expect(page.get_by_role("heading", name="CLI Token")).to_be_visible()
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
