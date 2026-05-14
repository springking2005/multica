from __future__ import annotations

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import expect

from accounts.models import Member, Workspace
from e2e.helpers.assertions import assert_htmx_loaded, assert_no_console_errors, assert_no_raw_json_page


@pytest.mark.django_db(transaction=True)
def test_login_page_loads_htmx(page, live_server):
    page.goto(live_server.url + "/login/")

    expect(page.get_by_role("heading", name="登录")).to_be_visible()
    expect(page.locator("#login-form[hx-post='/api/auth/login']")).to_be_visible()
    assert_htmx_loaded(page)
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_login_succeeds_without_raw_json(page, live_server):
    user_model = get_user_model()
    suffix = uuid4().hex[:8]
    user = user_model.objects.create_user(email=f"login-{suffix}@example.com", password="admin123", name="Login User")
    workspace = Workspace.objects.create(name=f"Login {suffix}", slug=f"login-{suffix}")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)

    page.goto(live_server.url + "/login/")
    page.get_by_placeholder("邮箱地址").fill(user.email)
    page.get_by_placeholder("密码").fill("admin123")
    with page.expect_response(lambda response: response.url.endswith("/api/auth/login") and response.status == 200):
        page.get_by_role("button", name="登录").click()
    page.wait_for_url("**/dashboard/")

    expect(page.locator("body")).not_to_contain_text('{"token"')
    assert page.evaluate("() => Boolean(localStorage.getItem('bodiagent_token'))")
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_register_succeeds_without_raw_json(page, live_server):
    suffix = uuid4().hex[:8]
    page.goto(live_server.url + "/register/")
    page.get_by_placeholder("姓名").fill("Register User")
    page.get_by_placeholder("邮箱地址").fill(f"register-{suffix}@example.com")
    page.get_by_placeholder("密码", exact=True).fill("admin123")
    page.get_by_placeholder("确认密码").fill("admin123")
    with page.expect_response(lambda response: response.url.endswith("/api/auth/register") and response.status == 201):
        page.get_by_role("button", name="注册").click()
    page.wait_for_url("**/dashboard/")

    expect(page.locator("body")).not_to_contain_text('{"token"')
    assert page.evaluate("() => Boolean(localStorage.getItem('bodiagent_token'))")
    assert_no_console_errors(
        page.console_errors,
        allow=[
            "Bad Request",
            "Response Status Error Code 400 from /api/issues",
            "Response Status Error Code 400 from /api/agents",
            "Response Status Error Code 400 from /api/inbox",
        ],
    )
