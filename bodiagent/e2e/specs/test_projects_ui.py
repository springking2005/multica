from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_project


@pytest.mark.django_db(transaction=True)
def test_projects_page_lists_seeded_project(page, live_server, browser_user):
    create_project(browser_user.workspace, "Browser Project")

    page.goto(live_server.url + "/projects/")

    expect(page.get_by_role("heading", name="项目")).to_be_visible()
    expect(page.locator("#project-surface")).to_contain_text("Browser Project", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_projects_create_dialog_validation_stays_on_page(page, live_server, browser_user):
    page.goto(live_server.url + "/projects/")

    page.get_by_role("button", name="新建项目").first.click()
    expect(page.locator("#project-form")).to_be_visible()
    page.locator("#project-form input[name='title']").fill("")
    page.locator("#project-submit-button").click()
    expect(page.locator("#project-dialog")).to_be_visible()
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
