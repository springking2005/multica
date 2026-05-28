from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_agent


@pytest.mark.django_db(transaction=True)
def test_agents_page_lists_seeded_agent(page, live_server, browser_user):
    create_agent(browser_user.workspace, "Browser Agent")

    page.goto(live_server.url + "/agents/")

    expect(page.get_by_role("heading", name="智能体")).to_be_visible()
    expect(page.locator("#agent-surface")).to_contain_text("Browser Agent", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_agents_page_lists_existing_agent_when_daemon_binding_is_missing(page, live_server, browser_user):
    agent = create_agent(browser_user.workspace, "Orphaned Browser Agent")
    agent.daemon.workspace_bindings.all().delete()

    page.goto(live_server.url + "/agents/")

    expect(page.get_by_role("heading", name="智能体")).to_be_visible()
    expect(page.locator("#agent-surface")).to_contain_text("Orphaned Browser Agent", timeout=10_000)
    expect(page.locator("#agent-surface")).to_contain_text("当前工作区没有可用 Daemon", timeout=10_000)
    expect(page.locator("#agent-surface")).to_contain_text("Daemon: 未绑定", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_agents_create_dialog_validation_stays_on_page(page, live_server, browser_user):
    page.goto(live_server.url + "/agents/")

    page.get_by_role("button", name="创建智能体", exact=True).click()
    expect(page.locator("#agent-form")).to_be_visible()
    page.locator("#agent-form details").click()
    page.locator("textarea[name='custom_env']").fill("{")
    page.locator("#agent-form button[type='submit']").click()
    expect(page.locator("#agent-form")).to_be_visible()
    expect(page.locator("#agent-form-error")).to_be_visible(timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)

@pytest.mark.django_db(transaction=True)
def test_agents_create_edit_archive_restore_delete_from_browser(page, live_server, browser_user):
    seeded = create_agent(browser_user.workspace, "Seed Agent")

    page.goto(live_server.url + "/agents/")
    expect(page.locator("#agent-surface")).to_contain_text("Seed Agent", timeout=10_000)

    page.get_by_role("button", name="创建智能体", exact=True).click()
    expect(page.locator("#agent-form")).to_be_visible()
    page.locator("#agent-form input[name='name']").fill("Browser CRUD Agent")
    page.locator("#agent-form input[name='description']").fill("Created through browser CRUD flow")
    page.locator("#agent_daemon_id").select_option(str(seeded.daemon_id))
    page.locator("#agent-form input[name='model']").fill("claude-crud-model")
    with page.expect_response(
        lambda response: response.url.rstrip("/").endswith("/api/agents") and response.status in {200, 201}
    ):
        page.locator("#agent-submit-button").click()
    expect(page.locator("#agent-surface")).to_contain_text("Browser CRUD Agent", timeout=10_000)

    row = page.locator("tr", has_text="Browser CRUD Agent")
    row.get_by_role("button", name="编辑").click()
    expect(page.locator("#agent-dialog-title")).to_contain_text("编辑智能体")
    page.locator("#agent-form input[name='name']").fill("Browser CRUD Agent Updated")
    page.locator("#agent-form input[name='max_concurrent_tasks']").fill("5")
    with page.expect_response(lambda response: "/api/agents/" in response.url and response.status == 200):
        page.locator("#agent-submit-button").click()
    expect(page.locator("#agent-surface")).to_contain_text("Browser CRUD Agent Updated", timeout=10_000)
    expect(page.locator("tr", has_text="Browser CRUD Agent Updated")).to_contain_text("5")

    page.locator("tr", has_text="Browser CRUD Agent Updated").get_by_role("button", name="归档").click()
    expect(page.locator("#agent-surface")).not_to_contain_text("Browser CRUD Agent Updated", timeout=10_000)
    page.locator("#agent-status-filter").select_option("archived")
    expect(page.locator("#agent-surface")).to_contain_text("Browser CRUD Agent Updated", timeout=10_000)

    page.locator("tr", has_text="Browser CRUD Agent Updated").get_by_role("button", name="恢复").click()
    expect(page.locator("#agent-surface")).not_to_contain_text("Browser CRUD Agent Updated", timeout=10_000)
    page.locator("#agent-status-filter").select_option("active")
    expect(page.locator("#agent-surface")).to_contain_text("Browser CRUD Agent Updated", timeout=10_000)

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("tr", has_text="Browser CRUD Agent Updated").get_by_role("button", name="删除").click()
    expect(page.locator("#agent-surface")).not_to_contain_text("Browser CRUD Agent Updated", timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
