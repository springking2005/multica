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

@pytest.mark.django_db(transaction=True)
def test_projects_create_edit_filter_delete_from_browser(page, live_server, browser_user):
    page.goto(live_server.url + "/projects/")

    page.get_by_role("button", name="新建项目").first.click()
    expect(page.locator("#project-form")).to_be_visible()
    page.locator("#project-form input[name='title']").fill("Browser CRUD Project")
    page.locator("#project-form textarea[name='description']").fill("Created from browser management flow")
    page.locator("#project-form input[name='icon']").fill("🚀")
    page.locator("#project-form select[name='priority']").select_option("high")
    with page.expect_response(
        lambda response: response.url.rstrip("/").endswith("/api/projects") and response.status in {200, 201}
    ):
        page.locator("#project-submit-button").click()
    expect(page.locator("#project-surface")).to_contain_text("Browser CRUD Project", timeout=10_000)
    expect(page.locator("tr", has_text="Browser CRUD Project")).to_contain_text("高")

    page.locator("tr", has_text="Browser CRUD Project").get_by_role("button", name="编辑").click()
    expect(page.locator("#project-dialog-title")).to_contain_text("编辑项目")
    page.locator("#project-form input[name='title']").fill("Browser CRUD Project Updated")
    page.locator("#project-form select[name='status']").select_option("in_progress")
    page.locator("#project-form select[name='priority']").select_option("urgent")
    with page.expect_response(lambda response: "/api/projects/" in response.url and response.status == 200):
        page.locator("#project-submit-button").click()
    expect(page.locator("#project-surface")).to_contain_text("Browser CRUD Project Updated", timeout=10_000)
    expect(page.locator("tr", has_text="Browser CRUD Project Updated")).to_contain_text("进行中")
    expect(page.locator("tr", has_text="Browser CRUD Project Updated")).to_contain_text("紧急")

    page.locator("#project-status-filter").select_option("completed")
    expect(page.locator("#project-surface")).not_to_contain_text("Browser CRUD Project Updated", timeout=10_000)
    page.locator("#project-status-filter").select_option("in_progress")
    expect(page.locator("#project-surface")).to_contain_text("Browser CRUD Project Updated", timeout=10_000)

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("tr", has_text="Browser CRUD Project Updated").get_by_role("button", name="删除").click()
    expect(page.locator("#project-surface")).not_to_contain_text("Browser CRUD Project Updated", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
