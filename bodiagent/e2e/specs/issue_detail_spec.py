from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_activity, create_issue


@pytest.mark.django_db(transaction=True)
def test_issue_detail_loads_updates_and_comments(page, live_server, browser_user):
    issue = create_issue(browser_user.workspace, browser_user.member, title="Detail issue", description="Detail body")
    create_activity(browser_user.workspace, issue, browser_user.member, action="created")

    page.goto(live_server.url + f"/issues/{issue.id}/")

    expect(page.locator("#issue-title-input")).to_have_value("Detail issue", timeout=10_000)
    expect(page.locator("#issue-description-input")).to_have_value("Detail body")
    assert_no_raw_json_page(page)

    page.locator("#issue-status-select").select_option("in_progress")
    expect(page.locator("#issue-save-state")).to_contain_text("已保存", timeout=10_000)
    page.reload()
    expect(page.locator("#issue-status-select")).to_have_value("in_progress", timeout=10_000)

    expect(page.locator("#comment-submit")).to_be_disabled()
    page.locator("#comment-content").fill("Browser comment <script>alert(1)</script>")
    with page.expect_response(lambda response: f"/api/issues/{issue.id}/comments" in response.url and response.status == 201):
        page.locator("#comment-submit").click()
    expect(page.locator("#comments-list")).to_contain_text("Browser comment")
    expect(page.locator("#comments-list")).to_contain_text("<script>alert(1)</script>")

    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
