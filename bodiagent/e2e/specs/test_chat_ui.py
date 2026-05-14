from __future__ import annotations

import pytest
from playwright.sync_api import Browser, expect

from chat.models import ChatMessage
from e2e.helpers.assertions import (
    assert_no_console_errors,
    assert_no_raw_json_page,
    collect_console_errors,
)
from e2e.helpers.data import BrowserUser, create_agent, create_chat_session, login_context_via_api


@pytest.mark.django_db(transaction=True)
def test_chat_page_loads_session_and_safe_transcript(asgi_page, asgi_live_server, browser_user):
    agent = create_agent(browser_user.workspace, "Browser Chat Agent")
    session = create_chat_session(browser_user.workspace, browser_user.member, agent)
    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_USER,
        content="hello <img src=x onerror=alert(1)>",
    )
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content="assistant reply")

    asgi_page.goto(asgi_live_server.url + f"/chat/{session.id}/")

    expect(asgi_page.get_by_role("heading", name="智能体聊天")).to_be_visible()
    expect(asgi_page.locator("#chat-status")).to_have_text("已连接", timeout=10_000)
    expect(asgi_page.locator("#chat-messages")).to_contain_text("hello <img", timeout=10_000)
    expect(asgi_page.locator("#chat-messages")).to_contain_text("assistant reply")
    expect(asgi_page.locator("#chat-input")).to_be_enabled()
    assert_no_raw_json_page(asgi_page)
    assert_no_console_errors(asgi_page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_chat_new_session_controls_are_usable(asgi_page, asgi_live_server, browser_user):
    create_agent(browser_user.workspace, "New Session Agent")
    asgi_page.goto(asgi_live_server.url + "/chat/")

    expect(asgi_page.locator("#chat-agent-select")).to_contain_text("New Session Agent", timeout=10_000)
    asgi_page.locator("#chat-agent-select").select_option(index=1)
    with asgi_page.expect_response(lambda response: response.url.endswith("/api/sessions/") and response.status == 201):
        asgi_page.locator("#chat-new-session").click()
    expect(asgi_page.locator("#chat-status")).to_have_text("已连接", timeout=10_000)
    expect(asgi_page.locator("#chat-input")).to_be_enabled()
    assert "/chat/" in asgi_page.url
    assert len(asgi_page.url.rstrip("/").split("/")) >= 4
    assert_no_raw_json_page(asgi_page)
    assert_no_console_errors(asgi_page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_chat_browser_websocket_sends_and_persists(asgi_page, asgi_live_server, browser_user):
    agent = create_agent(browser_user.workspace, "Sending Chat Agent")
    session = create_chat_session(browser_user.workspace, browser_user.member, agent)

    asgi_page.goto(asgi_live_server.url + f"/chat/{session.id}/")
    expect(asgi_page.locator("#chat-status")).to_have_text("已连接", timeout=10_000)

    asgi_page.locator("#chat-input").fill("Browser WS says <b>hello</b>")
    asgi_page.keyboard.press("Enter")

    expect(asgi_page.locator("#chat-messages")).to_contain_text("Browser WS says <b>hello</b>", timeout=10_000)
    assert ChatMessage.objects.filter(
        session=session,
        role=ChatMessage.ROLE_USER,
        content="Browser WS says <b>hello</b>",
    ).exists()
    assert_no_raw_json_page(asgi_page)
    assert_no_console_errors(asgi_page.console_errors)


@pytest.mark.django_db(transaction=True)
def test_chat_two_browser_pages_receive_broadcast(
    browser: Browser,
    asgi_live_server,
    browser_user: BrowserUser,
):
    agent = create_agent(browser_user.workspace, "Broadcast Chat Agent")
    session = create_chat_session(browser_user.workspace, browser_user.member, agent)
    pages = []
    contexts = []
    try:
        for _ in range(2):
            context = browser.new_context(base_url=asgi_live_server.url, viewport={"width": 1280, "height": 900})
            login_context_via_api(context, asgi_live_server.url, browser_user)
            page = context.new_page()
            page.console_errors = collect_console_errors(page)  # type: ignore[attr-defined]
            page.goto(asgi_live_server.url + f"/chat/{session.id}/")
            expect(page.locator("#chat-status")).to_have_text("已连接", timeout=10_000)
            contexts.append(context)
            pages.append(page)

        pages[0].locator("#chat-input").fill("Broadcast from page one")
        pages[0].keyboard.press("Enter")

        expect(pages[1].locator("#chat-messages")).to_contain_text("Broadcast from page one", timeout=10_000)
        assert ChatMessage.objects.filter(session=session, content="Broadcast from page one").exists()
        for page in pages:
            assert_no_raw_json_page(page)
            assert_no_console_errors(page.console_errors)
    finally:
        for context in contexts:
            context.close()
