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
