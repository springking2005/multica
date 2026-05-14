from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_htmx_loaded, assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_issue


@pytest.mark.django_db(transaction=True)
def test_issues_board_renders_api_cards(page, live_server, browser_user):
    create_issue(
        browser_user.workspace,
        browser_user.member,
        title="Browser board issue",
        status="backlog",
        priority="high",
    )

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


@pytest.mark.django_db(transaction=True)
def test_issues_board_quick_create_creates_card_and_opens_detail(page, live_server, browser_user):
    page.goto(live_server.url + "/issues/?quick_create=1")

    expect(page.locator("#issue-create-dialog")).to_be_visible(timeout=10_000)
    page.locator("#issue-create-form input[name='title']").fill("Quick created browser issue")
    page.locator("#issue-create-form textarea[name='description']").fill("Created from the kanban quick create dialog")
    page.locator("#issue-create-form select[name='status']").select_option("todo")
    page.locator("#issue-create-form select[name='priority']").select_option("high")
    with page.expect_response(
        lambda response: response.url.rstrip("/").endswith("/api/issues") and response.status == 201
    ):
        page.locator("#issue-create-submit").click()

    expect(page.locator("#issue-create-dialog")).to_be_hidden(timeout=10_000)
    card = page.locator(".kanban-column", has_text="待处理").locator(
        ".issue-card", has_text="Quick created browser issue"
    )
    expect(card).to_be_visible(timeout=10_000)
    expect(card).to_contain_text("高")

    card.click()
    expect(page.locator("#issue-title-input")).to_have_value("Quick created browser issue", timeout=10_000)
    expect(page.locator("#issue-description-input")).to_have_value("Created from the kanban quick create dialog")
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_issues_board_quick_create_validation_stays_in_dialog(page, live_server, browser_user):
    page.goto(live_server.url + "/issues/")

    page.get_by_role("button", name="新建 Issue").click()
    expect(page.locator("#issue-create-dialog")).to_be_visible(timeout=10_000)
    page.locator("#issue-create-submit").click()
    expect(page.locator("#issue-create-dialog")).to_be_visible()
    expect(page.locator("#issue-create-error")).to_contain_text("请输入 Issue 标题")
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
