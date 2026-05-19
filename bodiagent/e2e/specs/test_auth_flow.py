from __future__ import annotations

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import Browser, expect

from accounts.models import Member, Workspace
from e2e.helpers.assertions import (
    assert_htmx_loaded,
    assert_no_console_errors,
    assert_no_raw_json_page,
    collect_console_errors,
)


def _new_auth_page(browser: Browser, live_server):
    context = browser.new_context(base_url=live_server.url, viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.console_errors = collect_console_errors(page)  # type: ignore[attr-defined]
    return context, page


@pytest.mark.django_db(transaction=True)
def test_login_page_loads_htmx(browser, live_server):
    context, page = _new_auth_page(browser, live_server)
    try:
        page.goto(live_server.url + "/login/")

        expect(page.get_by_role("heading", name="登录")).to_be_visible()
        expect(page.locator("#login-form[hx-post='/api/auth/login']")).to_be_visible()
        assert_htmx_loaded(page)
        assert_no_raw_json_page(page)
        assert_no_console_errors(page.console_errors)
    finally:
        context.close()


@pytest.mark.django_db(transaction=True)
def test_login_failure_shows_error_without_raw_json(browser, live_server):
    context, page = _new_auth_page(browser, live_server)
    try:
        page.goto(live_server.url + "/login/")
        page.get_by_placeholder("邮箱地址").fill("missing-admin@example.com")
        page.get_by_placeholder("密码").fill("wrong-password")

        with page.expect_response(lambda response: response.url.endswith("/api/auth/login") and response.status == 400):
            page.get_by_role("button", name="登录").click()

        expect(page).to_have_url(live_server.url + "/login/")
        expect(page.get_by_role("alert")).to_contain_text("Invalid email or password")
        expect(page.locator("body")).not_to_contain_text('{"non_field_errors"')
        assert not page.evaluate("() => Boolean(localStorage.getItem('bodiagent_token'))")
        assert_no_raw_json_page(page)
        assert_no_console_errors(
            page.console_errors,
            allow=[
                "Bad Request",
                "Response Status Error Code 400 from /api/auth/login",
            ],
        )
    finally:
        context.close()


@pytest.mark.django_db(transaction=True)
def test_login_succeeds_without_raw_json(browser, live_server):
    user_model = get_user_model()
    suffix = uuid4().hex[:8]
    user = user_model.objects.create_user(email=f"login-{suffix}@example.com", password="admin123", name="Login User")
    workspace = Workspace.objects.create(name=f"Login {suffix}", slug=f"login-{suffix}")
    Member.objects.create(workspace=workspace, user=user, role=Member.ROLE_OWNER)

    context, page = _new_auth_page(browser, live_server)
    try:
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
    finally:
        context.close()


@pytest.mark.django_db(transaction=True)
def test_register_succeeds_without_raw_json(browser, live_server):
    suffix = uuid4().hex[:8]
    context, page = _new_auth_page(browser, live_server)
    try:
        page.goto(live_server.url + "/register/")
        page.get_by_placeholder("姓名").fill("Register User")
        page.get_by_placeholder("邮箱地址").fill(f"register-{suffix}@example.com")
        page.get_by_placeholder("密码", exact=True).fill("admin123")
        page.get_by_placeholder("确认密码").fill("admin123")
        with page.expect_response(
            lambda response: response.url.endswith("/api/auth/register") and response.status == 201
        ):
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
    finally:
        context.close()
