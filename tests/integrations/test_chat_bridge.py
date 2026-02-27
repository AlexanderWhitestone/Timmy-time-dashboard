"""Tests for the chat_bridge base classes, registry, and invite parser."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from integrations.chat_bridge.base import (
    ChatMessage,
    ChatPlatform,
    ChatThread,
    InviteInfo,
    PlatformState,
    PlatformStatus,
)
from integrations.chat_bridge.registry import PlatformRegistry


# ── Base dataclass tests ───────────────────────────────────────────────────────


class TestChatMessage:
    def test_create_message(self):
        msg = ChatMessage(
            content="Hello",
            author="user1",
            channel_id="123",
            platform="test",
        )
        assert msg.content == "Hello"
        assert msg.author == "user1"
        assert msg.platform == "test"
        assert msg.thread_id is None
        assert msg.attachments == []

    def test_message_with_thread(self):
        msg = ChatMessage(
            content="Reply",
            author="bot",
            channel_id="123",
            platform="discord",
            thread_id="456",
        )
        assert msg.thread_id == "456"


class TestChatThread:
    def test_create_thread(self):
        thread = ChatThread(
            thread_id="t1",
            title="Timmy | user1",
            channel_id="c1",
            platform="discord",
        )
        assert thread.thread_id == "t1"
        assert thread.archived is False
        assert thread.message_count == 0


class TestInviteInfo:
    def test_create_invite(self):
        invite = InviteInfo(
            url="https://discord.gg/abc123",
            code="abc123",
            platform="discord",
            source="qr",
        )
        assert invite.code == "abc123"
        assert invite.source == "qr"


class TestPlatformStatus:
    def test_to_dict(self):
        status = PlatformStatus(
            platform="discord",
            state=PlatformState.CONNECTED,
            token_set=True,
            guild_count=3,
        )
        d = status.to_dict()
        assert d["connected"] is True
        assert d["platform"] == "discord"
        assert d["guild_count"] == 3
        assert d["state"] == "connected"

    def test_disconnected_status(self):
        status = PlatformStatus(
            platform="test",
            state=PlatformState.DISCONNECTED,
            token_set=False,
        )
        d = status.to_dict()
        assert d["connected"] is False


# ── PlatformRegistry tests ────────────────────────────────────────────────────


class _FakePlatform(ChatPlatform):
    """Minimal ChatPlatform for testing the registry."""

    def __init__(self, platform_name: str = "fake"):
        self._name = platform_name
        self._state = PlatformState.DISCONNECTED

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> PlatformState:
        return self._state

    async def start(self, token=None) -> bool:
        self._state = PlatformState.CONNECTED
        return True

    async def stop(self) -> None:
        self._state = PlatformState.DISCONNECTED

    async def send_message(self, channel_id, content, thread_id=None):
        return ChatMessage(
            content=content, author="bot", channel_id=channel_id, platform=self._name
        )

    async def create_thread(self, channel_id, title, initial_message=None):
        return ChatThread(
            thread_id="t1", title=title, channel_id=channel_id, platform=self._name
        )

    async def join_from_invite(self, invite_code) -> bool:
        return True

    def status(self):
        return PlatformStatus(
            platform=self._name,
            state=self._state,
            token_set=False,
        )

    def save_token(self, token):
        pass

    def load_token(self):
        return None


class TestPlatformRegistry:
    def test_register_and_get(self):
        reg = PlatformRegistry()
        p = _FakePlatform("test1")
        reg.register(p)
        assert reg.get("test1") is p

    def test_get_missing(self):
        reg = PlatformRegistry()
        assert reg.get("nonexistent") is None

    def test_unregister(self):
        reg = PlatformRegistry()
        p = _FakePlatform("test1")
        reg.register(p)
        assert reg.unregister("test1") is True
        assert reg.get("test1") is None

    def test_unregister_missing(self):
        reg = PlatformRegistry()
        assert reg.unregister("nope") is False

    def test_list_platforms(self):
        reg = PlatformRegistry()
        reg.register(_FakePlatform("a"))
        reg.register(_FakePlatform("b"))
        statuses = reg.list_platforms()
        assert len(statuses) == 2
        names = {s.platform for s in statuses}
        assert names == {"a", "b"}

    @pytest.mark.asyncio
    async def test_start_all(self):
        reg = PlatformRegistry()
        reg.register(_FakePlatform("x"))
        reg.register(_FakePlatform("y"))
        results = await reg.start_all()
        assert results == {"x": True, "y": True}

    @pytest.mark.asyncio
    async def test_stop_all(self):
        reg = PlatformRegistry()
        p = _FakePlatform("z")
        reg.register(p)
        await reg.start_all()
        assert p.state == PlatformState.CONNECTED
        await reg.stop_all()
        assert p.state == PlatformState.DISCONNECTED

    def test_replace_existing(self):
        reg = PlatformRegistry()
        p1 = _FakePlatform("dup")
        p2 = _FakePlatform("dup")
        reg.register(p1)
        reg.register(p2)
        assert reg.get("dup") is p2


# ── InviteParser tests ────────────────────────────────────────────────────────


class TestInviteParser:
    def test_parse_text_discord_gg(self):
        from integrations.chat_bridge.invite_parser import invite_parser

        result = invite_parser.parse_text("Join us at https://discord.gg/abc123!")
        assert result is not None
        assert result.code == "abc123"
        assert result.platform == "discord"
        assert result.source == "text"

    def test_parse_text_discord_com_invite(self):
        from integrations.chat_bridge.invite_parser import invite_parser

        result = invite_parser.parse_text(
            "Link: https://discord.com/invite/myServer2024"
        )
        assert result is not None
        assert result.code == "myServer2024"

    def test_parse_text_discordapp(self):
        from integrations.chat_bridge.invite_parser import invite_parser

        result = invite_parser.parse_text(
            "https://discordapp.com/invite/test-code"
        )
        assert result is not None
        assert result.code == "test-code"

    def test_parse_text_no_invite(self):
        from integrations.chat_bridge.invite_parser import invite_parser

        result = invite_parser.parse_text("Hello world, no links here")
        assert result is None

    def test_parse_text_bare_discord_gg(self):
        from integrations.chat_bridge.invite_parser import invite_parser

        result = invite_parser.parse_text("discord.gg/xyz789")
        assert result is not None
        assert result.code == "xyz789"

    @pytest.mark.asyncio
    async def test_parse_image_no_deps(self):
        """parse_image returns None when pyzbar/Pillow are not installed."""
        from integrations.chat_bridge.invite_parser import InviteParser

        parser = InviteParser()
        # With mocked pyzbar, this should gracefully return None
        result = await parser.parse_image(b"fake-image-bytes")
        assert result is None


class TestExtractDiscordCode:
    def test_various_formats(self):
        from integrations.chat_bridge.invite_parser import _extract_discord_code

        assert _extract_discord_code("discord.gg/abc") == "abc"
        assert _extract_discord_code("https://discord.gg/test") == "test"
        assert _extract_discord_code("http://discord.gg/http") == "http"
        assert _extract_discord_code("discord.com/invite/xyz") == "xyz"
        assert _extract_discord_code("no link here") is None
        assert _extract_discord_code("") is None
