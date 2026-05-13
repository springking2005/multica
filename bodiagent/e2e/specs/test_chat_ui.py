from __future__ import annotations

import pytest
from playwright.sync_api import expect

from chat.models import ChatMessage
from e2e.helpers.assertions import assert_no_console_errors, assert_no_raw_json_page
from e2e.helpers.data import create_agent, create_chat_session


@pytest.mark.django_db(transaction=True)
def test_chat_page_loads_session_and_safe_transcript(page, live_server, browser_user):
    agent = create_agent(browser_user.workspace, "Browser Chat Agent")
    session = create_chat_session(browser_user.workspace, browser_user.member, agent)
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="hello <img src=x onerror=alert(1)>")
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, content="assistant reply")

    page.goto(live_server.url + f"/chat/{session.id}/")

    expect(page.get_by_role("heading", name="智能体聊天")).to_be_visible()
    expect(page.locator("#chat-messages")).to_contain_text("hello <img", timeout=10_000)
    expect(page.locator("#chat-messages")).to_contain_text("assistant reply")
    expect(page.locator("#chat-input")).to_be_disabled()
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors, allow=["WebSocket connection to", "/ws/chat/", "Unexpected response code: 404"])


@pytest.mark.django_db(transaction=True)
def test_chat_new_session_controls_are_usable(page, live_server, browser_user):
    create_agent(browser_user.workspace, "New Session Agent")
    page.goto(live_server.url + "/chat/")

    expect(page.locator("#chat-agent-select")).to_contain_text("New Session Agent", timeout=10_000)
    page.locator("#chat-agent-select").select_option(index=1)
    with page.expect_response(lambda response: response.url.endswith("/api/sessions/") and response.status == 201):
      page.locator("#chat-new-session").click()
    assert "/chat/" in page.url
    assert len(page.url.rstrip("/").split("/")) >= 4
    assert_no_raw_json_page(page)
    assert_no_console_errors(page.console_errors)
