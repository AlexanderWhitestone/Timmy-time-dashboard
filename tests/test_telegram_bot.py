"""Tests for the Telegram bot integration."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── TelegramBot unit tests ────────────────────────────────────────────────────


class TestTelegramBotTokenHelpers:
    def test_save_and_load_token(self, tmp_path, monkeypatch):
        """save_token persists to disk; load_token reads it back."""
        state_file = tmp_path / "telegram_state.json"
        monkeypatch.setattr("telegram_bot.bot._STATE_FILE", state_file)

        from telegram_bot.bot import TelegramBot
        bot = TelegramBot()

        bot.save_token("test-token-123")
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["token"] == "test-token-123"

        loaded = bot.load_token()
        assert loaded == "test-token-123"

    def test_load_token_missing_file(self, tmp_path, monkeypatch):
        """load_token returns None when no state file and no env var."""
        state_file = tmp_path / "missing_telegram_state.json"
        monkeypatch.setattr("telegram_bot.bot._STATE_FILE", state_file)

        # Ensure settings.telegram_token is empty
        mock_settings = MagicMock()
        mock_settings.telegram_token = ""
        with patch("telegram_bot.bot._load_token_from_file", return_value=None):
            with patch("config.settings", mock_settings):
                from telegram_bot.bot import TelegramBot
                bot = TelegramBot()
                result = bot.load_token()
        assert result is None

    def test_token_set_property(self):
        """token_set reflects whether a token has been applied."""
        from telegram_bot.bot import TelegramBot
        bot = TelegramBot()
        assert not bot.token_set
        bot._token = "tok"
        assert bot.token_set

    def test_is_running_property(self):
        from telegram_bot.bot import TelegramBot
        bot = TelegramBot()
        assert not bot.is_running
        bot._running = True
        assert bot.is_running


class TestTelegramBotLifecycle:
    @pytest.mark.asyncio
    async def test_start_no_token_returns_false(self, tmp_path, monkeypatch):
        """start() returns False and stays idle when no token is available."""
        state_file = tmp_path / "telegram_state.json"
        monkeypatch.setattr("telegram_bot.bot._STATE_FILE", state_file)

        from telegram_bot.bot import TelegramBot
        bot = TelegramBot()
        with patch.object(bot, "load_token", return_value=None):
            result = await bot.start()
        assert result is False
        assert not bot.is_running

    @pytest.mark.asyncio
    async def test_start_already_running_returns_true(self):
        from telegram_bot.bot import TelegramBot
        bot = TelegramBot()
        bot._running = True
        result = await bot.start(token="any")
        assert result is True

    @pytest.mark.asyncio
    async def test_start_import_error_returns_false(self):
        """start() returns False gracefully when python-telegram-bot absent."""
        from telegram_bot.bot import TelegramBot
        bot = TelegramBot()

        with patch.object(bot, "load_token", return_value="tok"), \
             patch.dict("sys.modules", {"telegram": None, "telegram.ext": None}):
            result = await bot.start(token="tok")
        assert result is False
        assert not bot.is_running

    @pytest.mark.asyncio
    async def test_stop_when_not_running_is_noop(self):
        from telegram_bot.bot import TelegramBot
        bot = TelegramBot()
        # Should not raise
        await bot.stop()

    @pytest.mark.asyncio
    async def test_stop_calls_shutdown(self):
        """stop() invokes the Application shutdown sequence."""
        from telegram_bot.bot import TelegramBot
        bot = TelegramBot()
        bot._running = True

        mock_updater = AsyncMock()
        mock_app = AsyncMock()
        mock_app.updater = mock_updater
        bot._app = mock_app

        await bot.stop()

        mock_updater.stop.assert_awaited_once()
        mock_app.stop.assert_awaited_once()
        mock_app.shutdown.assert_awaited_once()
        assert not bot.is_running


# ── Dashboard route tests ─────────────────────────────────────────────────────


class TestTelegramRoutes:
    def test_status_not_running(self, client):
        """GET /telegram/status returns running=False when bot is idle."""
        from telegram_bot.bot import telegram_bot
        telegram_bot._running = False
        telegram_bot._token = None

        resp = client.get("/telegram/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is False
        assert data["token_set"] is False

    def test_status_running(self, client):
        """GET /telegram/status returns running=True when bot is active."""
        from telegram_bot.bot import telegram_bot
        telegram_bot._running = True
        telegram_bot._token = "tok"

        resp = client.get("/telegram/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["token_set"] is True

        # Cleanup
        telegram_bot._running = False
        telegram_bot._token = None

    def test_setup_empty_token(self, client):
        """POST /telegram/setup with empty token returns error."""
        resp = client.post("/telegram/setup", json={"token": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "empty" in data["error"].lower()

    def test_setup_success(self, client):
        """POST /telegram/setup with valid token starts bot and returns ok."""
        from telegram_bot.bot import telegram_bot

        telegram_bot._running = False
        with patch.object(telegram_bot, "save_token") as mock_save, \
             patch.object(telegram_bot, "start", new_callable=AsyncMock, return_value=True):
            resp = client.post("/telegram/setup", json={"token": "bot123:abc"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        mock_save.assert_called_once_with("bot123:abc")

    def test_setup_failure(self, client):
        """POST /telegram/setup returns error dict when bot fails to start."""
        from telegram_bot.bot import telegram_bot

        telegram_bot._running = False
        with patch.object(telegram_bot, "save_token"), \
             patch.object(telegram_bot, "start", new_callable=AsyncMock, return_value=False):
            resp = client.post("/telegram/setup", json={"token": "bad-token"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "error" in data

    def test_setup_stops_running_bot_first(self, client):
        """POST /telegram/setup stops any running bot before starting new one."""
        from telegram_bot.bot import telegram_bot
        telegram_bot._running = True

        with patch.object(telegram_bot, "save_token"), \
             patch.object(telegram_bot, "stop", new_callable=AsyncMock) as mock_stop, \
             patch.object(telegram_bot, "start", new_callable=AsyncMock, return_value=True):
            resp = client.post("/telegram/setup", json={"token": "new-token"})

        mock_stop.assert_awaited_once()
        assert resp.json()["ok"] is True
        telegram_bot._running = False


# ── Module singleton test ─────────────────────────────────────────────────────


def test_module_singleton_exists():
    """telegram_bot module exposes a singleton TelegramBot instance."""
    from telegram_bot.bot import telegram_bot, TelegramBot
    assert isinstance(telegram_bot, TelegramBot)
