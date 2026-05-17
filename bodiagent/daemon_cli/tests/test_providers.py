"""Tests for providers module."""

import pytest

from daemon_cli.providers import get_provider
from daemon_cli.providers.base import Event
from daemon_cli.providers.claude import ClaudeProvider
from daemon_cli.providers.codex import CodexProvider
from daemon_cli.providers.openclaw import OpenClawProvider


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


class TestClaudeStreamParser:
    @pytest.mark.asyncio
    async def test_parse_claude_v2_message_content(self):
        class Stdout:
            def __init__(self):
                self.lines = [
                    b'{"type":"assistant","message":{"content":[{"type":"text","text":"hello"}]}}\n',
                    b'{"type":"result","usage":{"input_tokens":1,"output_tokens":2},"model":"test","duration_ms":3}\n',
                    b'',
                ]

            async def readline(self):
                return self.lines.pop(0)

        class Proc:
            stdout = Stdout()

        from daemon_cli.providers.claude import _parse_claude_stream

        events = [event async for event in _parse_claude_stream(Proc())]

        assert events[0].type == "text"
        assert events[0].content == "hello"
        assert events[1].type == "status"
        assert events[1].metadata["input_tokens"] == 1
        assert events[1].metadata["output_tokens"] == 2

    @pytest.mark.asyncio
    async def test_claude_args_use_text_input_and_verbose_stream_json(self, monkeypatch):
        # Guard the CLI contract found during A4 verification: Claude Code v2
        # requires --verbose with stream-json and plain -p prompts must not be
        # combined with --input-format stream-json.
        captured_args = []

        class Stdout:
            def __init__(self):
                self.lines = [
                    b'{"type":"result","usage":{},"model":"test","duration_ms":1}\n',
                    b"",
                ]

            async def readline(self):
                return self.lines.pop(0)

        class Proc:
            stdout = Stdout()
            returncode = 0

            async def wait(self):
                return 0

        async def fake_create_subprocess_exec(*args, **kwargs):
            captured_args.extend(args)
            return Proc()

        monkeypatch.setattr("daemon_cli.providers.claude.asyncio.create_subprocess_exec", fake_create_subprocess_exec)

        events = [event async for event in ClaudeProvider("claude").execute("hello")]

        assert events[-1].type == "status"
        assert captured_args == ["claude", "-p", "hello", "--output-format", "stream-json", "--verbose"]
