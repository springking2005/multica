from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_htmx_loaded, assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_inbox_item, create_issue


@pytest.mark.django_db(transaction=True)
def test_inbox_lists_marks_read_and_navigates_to_issue(page, live_server, browser_user):
    issue = create_issue(browser_user.workspace, browser_user.member, title="Inbox linked issue")
    item = create_inbox_item(
        browser_user.workspace,
        browser_user.member,
        title="Inbox browser notification",
        body="Clicking should mark read and keep a valid link",
        issue=issue,
        read=False,
    )

    page.goto(live_server.url + "/inbox/")

    assert_htmx_loaded(page)
    expect(page.get_by_role("heading", name="收件箱")).to_be_visible()
    row = page.locator("#inbox-list .inbox-item", has_text="Inbox browser notification")
    expect(row).to_be_visible(timeout=10_000)
    expect(page.locator("#inbox-unread-count")).to_have_text("1")

    row.click()
    page.wait_for_url(f"**/issues/{issue.id}/")
    item.refresh_from_db()
    assert item.read is True
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_inbox_bulk_actions_update_list_without_raw_json(page, live_server, browser_user):
    first = create_inbox_item(browser_user.workspace, browser_user.member, title="Bulk unread one")
    second = create_inbox_item(browser_user.workspace, browser_user.member, title="Bulk unread two")

    page.goto(live_server.url + "/inbox/")

    expect(page.locator("#inbox-unread-count")).to_have_text("2", timeout=10_000)
    page.get_by_role("button", name="全部已读").click()
    expect(page.locator("#inbox-unread-count")).to_have_text("0", timeout=10_000)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.read is True
    assert second.read is True

    page.get_by_role("button", name="归档已读").click()
    expect(page.locator("#inbox-list")).to_contain_text("收件箱为空", timeout=10_000)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.archived is True
    assert second.archived is True
    expect(page.locator("body")).not_to_contain_text('"updated"')
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_inbox_empty_and_mobile_controls(page, live_server, browser_user):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(live_server.url + "/inbox/")

    expect(page.get_by_role("heading", name="收件箱")).to_be_visible()
    expect(page.get_by_role("button", name="全部已读")).to_be_visible()
    expect(page.get_by_role("button", name="归档已读")).to_be_visible()
    expect(page.locator("#inbox-list")).to_contain_text("收件箱为空", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
