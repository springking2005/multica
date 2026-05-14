from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_htmx_loaded, assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_agent, create_inbox_item, create_issue


@pytest.mark.django_db(transaction=True)
def test_dashboard_renders_stats_activity_and_my_issues(page, live_server, browser_user):
    create_agent(browser_user.workspace, "Dashboard Agent")
    assigned_issue = create_issue(
        browser_user.workspace,
        browser_user.member,
        title="Dashboard assigned issue",
        status="todo",
        assignee_type="member",
        assignee_id=browser_user.member.id,
    )
    create_issue(browser_user.workspace, browser_user.member, title="Dashboard backlog issue", status="backlog")
    create_inbox_item(
        browser_user.workspace,
        browser_user.member,
        title="Dashboard inbox notice",
        body="A browser-visible notification",
        issue=assigned_issue,
    )

    page.goto(live_server.url + "/dashboard/")

    assert_htmx_loaded(page)
    expect(page.locator("h1", has_text="你好,")).to_be_visible()
    expect(page.locator("#stat-open")).to_have_text("2", timeout=10_000)
    expect(page.locator("#stat-mine")).to_have_text("1")
    expect(page.locator("#stat-agents")).to_have_text("1")
    expect(page.locator("#dashboard-activity")).to_contain_text("Dashboard inbox notice")
    expect(page.locator("#dashboard-my-issues")).to_contain_text("Dashboard assigned issue")
    expect(page.locator("body")).not_to_contain_text('"results"')
    expect(page.locator("body")).not_to_contain_text('"items"')
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_dashboard_mobile_actions_are_reachable(page, live_server, browser_user):
    create_agent(browser_user.workspace, "Mobile Dashboard Agent")
    page.set_viewport_size({"width": 375, "height": 812})

    page.goto(live_server.url + "/dashboard/")

    expect(page.get_by_role("link", name="创建 Issue")).to_be_visible()
    expect(page.locator("#dashboard-activity")).to_be_visible()
    expect(page.locator("#dashboard-my-issues")).to_be_visible()
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
