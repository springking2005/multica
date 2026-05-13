"""Tests for providers module."""

import pytest

from daemon_cli.providers import detect_providers, get_provider
from daemon_cli.providers.base import Event, Provider
from daemon_cli.providers.claude import ClaudeProvider
from daemon_cli.providers.openclaw import OpenClawProvider
from daemon_cli.providers.codex import CodexProvider


class TestProviderABC:
    def test_event_dataclass(self):
        event = Event(type="text", content="hello")
        assert event.type == "text"
        assert event.content == "hello"
        assert event.tool == ""
        assert event.input == {}
        assert event.output == ""

    def test_event_defaults(self):
        event = Event(type="status")
        assert event.content == ""
        assert event.metadata == {}


class TestProviderInstantiation:
    def test_claude_provider_name(self):
        p = ClaudeProvider("claude")
        assert p.name == "claude"

    def test_openclaw_provider_name(self):
        p = OpenClawProvider("openclaw")
        assert p.name == "openclaw"

    def test_codex_provider_name(self):
        p = CodexProvider("codex")
        assert p.name == "codex"


class TestGetProvider:
    def test_get_claude(self):
        p = get_provider("claude")
        assert isinstance(p, ClaudeProvider)

    def test_get_openclaw(self):
        p = get_provider("openclaw")
        assert isinstance(p, OpenClawProvider)

    def test_get_codex(self):
        p = get_provider("codex")
        assert isinstance(p, CodexProvider)

    def test_get_with_custom_executable(self):
        p = get_provider("claude", executable="/usr/local/bin/claude")
        assert p.executable == "/usr/local/bin/claude"

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent")
