from __future__ import annotations

import os
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import Browser, expect

from accounts.models import Member, Workspace
from agents.models import Task
from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page, collect_console_errors
from e2e.helpers.data import (
    create_agent,
    create_autopilot,
    create_chat_session,
    create_inbox_item,
    create_issue,
    create_project,
    force_login_context,
    login_context_via_api,
)
from inbox.models import InboxItem
from issues.models import IssueDependency, IssueLabel, IssueToLabel

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.manual_audit,
    pytest.mark.skipif(
        os.environ.get("BODIAGENT_MANUAL_AUDIT") != "1",
        reason="manual browser audit is discovery-style and must be explicitly enabled",
    ),
]


def _new_no_workspace_context(browser: Browser, live_server):
    user_model = get_user_model()
    suffix = uuid4().hex[:8]
    user = user_model.objects.create_user(email=f"no-ws-{suffix}@example.com", password="admin123", name="No Workspace")
    context = browser.new_context(base_url=live_server.url, viewport={"width": 1280, "height": 900})
    workspace = Workspace.objects.create(name=f"Temp {suffix}", slug=f"temp-{suffix}")
    member = Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)
    force_login_context(context, live_server.url, user, workspace)
    member.delete()
    workspace.delete()
    page = context.new_page()
    page.console_errors = collect_console_errors(page)  # type: ignore[attr-defined]
    return context, page


@pytest.mark.django_db(transaction=True)
def test_manual_browser_system_audit_acceptance(page, live_server, asgi_live_server, browser_user, browser: Browser):
    project = create_project(browser_user.workspace, "Manual Audit Project")
    second_project = create_project(browser_user.workspace, "Manual Second Project")
    issue = create_issue(
        browser_user.workspace,
        browser_user.member,
        title="Manual Audit Issue",
        description="Seeded for manual browser audit",
        status="todo",
        project=project,
        assignee_type="member",
        assignee_id=browser_user.member.id,
    )
    child = create_issue(browser_user.workspace, browser_user.member, title="Manual Child Issue", parent_issue=issue)
    sibling = create_issue(browser_user.workspace, browser_user.member, title="Manual Dependency Issue")
    IssueDependency.objects.create(issue=issue, depends_on=sibling, type="related")
    label = IssueLabel.objects.create(workspace=browser_user.workspace, name="manual-audit", color="#2563EB")
    extra_label = IssueLabel.objects.create(workspace=browser_user.workspace, name="manual-extra", color="#16A34A")
    IssueToLabel.objects.create(issue=issue, label=label)
    agent = create_agent(browser_user.workspace, "Manual Audit Agent")
    Task.objects.create(agent=agent, issue=issue, daemon=agent.daemon, status=Task.Status.RUNNING)
    chat = create_chat_session(browser_user.workspace, browser_user.member, agent)
    create_autopilot(browser_user.workspace, browser_user.member, agent)
    unread = create_inbox_item(browser_user.workspace, browser_user.member, "Manual unread inbox", issue=issue, read=False)
    completed = create_inbox_item(
        browser_user.workspace,
        browser_user.member,
        "Manual completed task inbox",
        issue=issue,
        read=True,
        inbox_type=InboxItem.Type.TASK_COMPLETED,
    )

    page.goto(live_server.url + "/dashboard/")
    expect(page.get_by_role("heading").first).to_be_visible(timeout=10_000)
    expect(page.locator("aside a[href='/chat/'], aside a[href='/chat']")).to_be_visible()
    expect(page.locator("aside a[href='/inbox/'], aside a[href='/inbox']")).to_contain_text("1", timeout=10_000)

    my_issues_response = page.goto(live_server.url + "/my-issues")
    assert my_issues_response is not None and my_issues_response.status < 400
    expect(page.get_by_role("heading", name="我的 Issues")).to_be_visible(timeout=10_000)
    expect(page.locator("body")).to_contain_text("Manual Audit Issue", timeout=10_000)
    assert_no_raw_json_page(page)

    page.goto(live_server.url + "/projects/")
    expect(page.get_by_role("heading", name="项目")).to_be_visible(timeout=10_000)
    expect(page.locator("#project-surface")).to_contain_text("Manual Audit Project", timeout=10_000)
    expect(page.locator("#project-surface a", has_text="Manual Audit Project")).to_be_visible()
    expect(page.locator("#project-surface")).to_contain_text("1 个 Issue", timeout=10_000)
    expect(page.locator("#project-surface")).not_to_contain_text("占位")
    expect(page.locator("#project-surface")).not_to_contain_text("未接入")

    project_detail_response = page.goto(live_server.url + f"/projects/{project.id}/")
    assert project_detail_response is not None and project_detail_response.status < 400
    expect(page.get_by_role("heading", name="Manual Audit Project")).to_be_visible(timeout=10_000)
    expect(page.locator("body")).to_contain_text("Manual Audit Issue", timeout=10_000)
    expect(page.locator("body")).to_contain_text("进度")
    assert_no_raw_json_page(page)

    page.goto(live_server.url + "/issues/")
    expect(page.get_by_role("heading", name="Issue 看板")).to_be_visible(timeout=10_000)
    page.get_by_role("button", name="新建 Issue").click()
    expect(page.locator("#issue-create-dialog")).to_be_visible(timeout=10_000)
    expect(page.locator("#issue-create-form select[name='assignee_id']")).to_be_visible()
    expect(page.locator("#issue-create-form select[name='project']")).to_be_visible()
    page.locator("#issue-create-form input[name='title']").fill("Manual created with owner and project")
    page.locator("#issue-create-form select[name='assignee_type']").select_option("agent")
    page.locator("#issue-create-form select[name='assignee_id']").select_option(str(agent.id))
    page.locator("#issue-create-form select[name='project']").select_option(str(second_project.id))
    with page.expect_response(lambda response: response.url.rstrip("/").endswith("/api/issues") and response.status == 201):
        page.locator("#issue-create-submit").click()
    expect(page.locator("#issue-create-dialog")).to_be_hidden(timeout=10_000)

    page.goto(live_server.url + f"/issues/{issue.id}/")
    expect(page.locator("#issue-title-input")).to_have_value("Manual Audit Issue", timeout=10_000)
    expect(page.locator("#issue-assignee-id")).to_have_js_property("tagName", "SELECT")
    expect(page.locator("#issue-project-id")).to_have_js_property("tagName", "SELECT")
    page.locator("#issue-assignee-type").select_option("agent")
    page.locator("#issue-assignee-id").select_option(str(agent.id))
    with page.expect_response(lambda response: f"/api/issues/{issue.id}" in response.url and response.status == 200):
        page.locator("#issue-assignee-save").click()
    expect(page.locator("#issue-save-state")).to_contain_text("已保存", timeout=10_000)
    page.locator("#issue-project-id").select_option(str(second_project.id))
    with page.expect_response(lambda response: f"/api/issues/{issue.id}" in response.url and response.status == 200):
        page.locator("#issue-project-save").click()
    expect(page.locator("#issue-save-state")).to_contain_text("已保存", timeout=10_000)

    expect(page.locator("#issue-label-add")).to_be_visible(timeout=10_000)
    page.locator("#issue-label-add").select_option(str(extra_label.id))
    with page.expect_response(lambda response: f"/api/issues/{issue.id}/labels" in response.url and response.status == 201):
        page.locator("#issue-label-add-button").click()
    expect(page.locator("#issue-labels")).to_contain_text("manual-extra", timeout=10_000)
    with page.expect_response(lambda response: f"/api/issues/{issue.id}/labels" in response.url and response.status == 200):
        page.locator("#issue-labels").get_by_role("button", name="移除 manual-extra").click()
    expect(page.locator("#issue-labels")).not_to_contain_text("manual-extra", timeout=10_000)

    expect(page.locator("#issue-children-list")).to_contain_text("Manual Child Issue", timeout=10_000)
    expect(page.locator("#issue-dependencies-list")).to_contain_text("Manual Dependency Issue", timeout=10_000)
    expect(page.locator("#issue-delete-button")).to_be_visible()

    page.goto(live_server.url + f"/agents/{agent.id}/")
    expect(page.get_by_role("heading", name="Manual Audit Agent")).to_be_visible(timeout=10_000)
    expect(page.locator("#agent-task-history")).to_contain_text("running", timeout=10_000)
    expect(page.locator("#agent-task-history")).to_contain_text("Manual Audit Issue", timeout=10_000)

    page.goto(live_server.url + "/inbox/")
    expect(page.get_by_role("heading", name="收件箱")).to_be_visible(timeout=10_000)
    expect(page.locator("#inbox-list")).to_contain_text("Manual unread inbox", timeout=10_000)
    expect(page.locator("#inbox-list button", has_text="归档").first).to_be_visible()
    with page.expect_response(lambda response: f"/api/inbox/{unread.id}/archive" in response.url and response.status == 200):
        page.locator(f"[data-inbox-id='{unread.id}']").get_by_role("button", name="归档").click()
    expect(page.locator("#inbox-list")).not_to_contain_text("Manual unread inbox", timeout=10_000)
    expect(page.locator("aside a[href='/inbox/'], aside a[href='/inbox']")).to_contain_text("0", timeout=10_000)
    expect(page.get_by_role("button", name="归档已完成任务")).to_be_visible()
    with page.expect_response(lambda response: response.url.endswith("/api/inbox/archive-completed") and response.status == 200):
        page.get_by_role("button", name="归档已完成任务").click()
    expect(page.locator("#inbox-list")).not_to_contain_text("Manual completed task inbox", timeout=10_000)
    completed.refresh_from_db()
    assert completed.archived is True

    chat_context = browser.new_context(base_url=asgi_live_server.url, viewport={"width": 1280, "height": 900})
    login_context_via_api(chat_context, asgi_live_server.url, browser_user)
    chat_page = chat_context.new_page()
    chat_page.console_errors = collect_console_errors(chat_page)  # type: ignore[attr-defined]
    try:
        chat_page.goto(asgi_live_server.url + f"/chat/{chat.id}/")
        expect(chat_page.get_by_role("heading", name="智能体聊天")).to_be_visible(timeout=10_000)
        expect(chat_page.locator("#chat-status")).to_have_text("已连接", timeout=10_000)
        assert_no_console_errors(chat_page.console_errors)
    finally:
        chat_context.close()

    page.goto(live_server.url + "/autopilots/")
    expect(page.get_by_role("heading", name="自动驾驶")).to_be_visible(timeout=10_000)
    expect(page.locator("#autopilot-list")).to_contain_text("E2E Autopilot", timeout=10_000)
    page.goto(live_server.url + "/settings/")
    expect(page.get_by_role("heading", name="个人设置")).to_be_visible(timeout=10_000)

    context2, page2 = _new_no_workspace_context(browser, live_server)
    try:
        page2.goto(live_server.url + "/projects/")
        expect(page2.locator("body")).to_contain_text("创建工作区", timeout=10_000)
    finally:
        context2.close()

    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(live_server.url + "/projects/")
    expect(page.get_by_role("heading", name="项目")).to_be_visible(timeout=10_000)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
