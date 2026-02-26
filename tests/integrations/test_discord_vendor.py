"""Tests for the Discord vendor and dashboard routes."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from integrations.chat_bridge.base import PlatformState


# ── DiscordVendor unit tests ──────────────────────────────────────────────────


class TestDiscordVendor:
    def test_name(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        assert vendor.name == "discord"

    def test_initial_state(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        assert vendor.state == PlatformState.DISCONNECTED

    def test_status_disconnected(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        status = vendor.status()
        assert status.platform == "discord"
        assert status.state == PlatformState.DISCONNECTED
        assert status.token_set is False
        assert status.guild_count == 0

    def test_save_and_load_token(self, tmp_path, monkeypatch):
        from integrations.chat_bridge.vendors import discord as discord_mod
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        state_file = tmp_path / "discord_state.json"
        monkeypatch.setattr(discord_mod, "_STATE_FILE", state_file)

        vendor = DiscordVendor()
        vendor.save_token("test-token-abc")

        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["token"] == "test-token-abc"

        loaded = vendor.load_token()
        assert loaded == "test-token-abc"

    def test_load_token_missing_file(self, tmp_path, monkeypatch):
        from integrations.chat_bridge.vendors import discord as discord_mod
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        state_file = tmp_path / "nonexistent.json"
        monkeypatch.setattr(discord_mod, "_STATE_FILE", state_file)

        vendor = DiscordVendor()
        # Falls back to config.settings.discord_token
        token = vendor.load_token()
        # Default discord_token is "" which becomes None
        assert token is None

    @pytest.mark.asyncio
    async def test_start_no_token(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        result = await vendor.start(token=None)
        assert result is False

    @pytest.mark.asyncio
    async def test_start_import_error(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        # Simulate discord.py not installed by making import fail
        with patch.dict("sys.modules", {"discord": None}):
            result = await vendor.start(token="fake-token")
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_when_disconnected(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        # Should not raise
        await vendor.stop()
        assert vendor.state == PlatformState.DISCONNECTED

    def test_get_oauth2_url_no_client(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        assert vendor.get_oauth2_url() is None

    def test_get_oauth2_url_with_client(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        mock_client = MagicMock()
        mock_client.user.id = 123456789
        vendor._client = mock_client
        url = vendor.get_oauth2_url()
        assert "123456789" in url
        assert "oauth2/authorize" in url

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        result = await vendor.send_message("123", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_thread_not_connected(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        result = await vendor.create_thread("123", "Test Thread")
        assert result is None

    @pytest.mark.asyncio
    async def test_join_from_invite_not_connected(self):
        from integrations.chat_bridge.vendors.discord import DiscordVendor

        vendor = DiscordVendor()
        result = await vendor.join_from_invite("abc123")
        assert result is False


class TestChunkMessage:
    def test_short_message(self):
        from integrations.chat_bridge.vendors.discord import _chunk_message

        chunks = _chunk_message("Hello!", 2000)
        assert chunks == ["Hello!"]

    def test_long_message(self):
        from integrations.chat_bridge.vendors.discord import _chunk_message

        text = "a" * 5000
        chunks = _chunk_message(text, 2000)
        assert len(chunks) == 3
        assert all(len(c) <= 2000 for c in chunks)
        assert "".join(chunks) == text

    def test_split_at_newline(self):
        from integrations.chat_bridge.vendors.discord import _chunk_message

        text = "Line1\n" + "x" * 1990 + "\nLine3"
        chunks = _chunk_message(text, 2000)
        assert len(chunks) >= 2
        assert chunks[0].startswith("Line1")


# ── Discord route tests ───────────────────────────────────────────────────────


class TestDiscordRoutes:
    def test_status_endpoint(self, client):
        resp = client.get("/discord/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "discord"
        assert "connected" in data

    def test_setup_empty_token(self, client):
        resp = client.post("/discord/setup", json={"token": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "empty" in data["error"].lower()

    def test_setup_with_token(self, client):
        """Setup with a token — bot won't actually connect but route works."""
        with patch(
            "integrations.chat_bridge.vendors.discord.DiscordVendor.start",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = client.post(
                "/discord/setup", json={"token": "fake-token-123"}
            )
        assert resp.status_code == 200
        data = resp.json()
        # Will fail because discord.py is mocked, but route handles it
        assert "ok" in data

    def test_join_no_input(self, client):
        resp = client.post("/discord/join")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "no discord invite" in data["error"].lower()

    def test_join_with_text_invite(self, client):
        with patch(
            "integrations.chat_bridge.vendors.discord.DiscordVendor.join_from_invite",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = client.post(
                "/discord/join",
                data={"invite_url": "https://discord.gg/testcode"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["invite"]["code"] == "testcode"
        assert data["invite"]["source"] == "text"

    def test_oauth_url_not_connected(self, client):
        from integrations.chat_bridge.vendors.discord import discord_bot

        # Reset singleton so it has no client
        discord_bot._client = None
        resp = client.get("/discord/oauth-url")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
