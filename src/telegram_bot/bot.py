"""Telegram bot integration for Timmy Time.

Bridges Telegram messages to Timmy (the local AI agent).  The bot token
is supplied via the dashboard setup endpoint or the TELEGRAM_TOKEN env var.

Optional dependency — install with:
    pip install ".[telegram]"
"""

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# State file lives in the project root alongside timmy.db
_STATE_FILE = Path(__file__).parent.parent.parent / "telegram_state.json"


def _load_token_from_file() -> str | None:
    """Read the saved bot token from the state file."""
    try:
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text())
            return data.get("token") or None
    except Exception as exc:
        logger.debug("Could not read telegram state file: %s", exc)
    return None


def _save_token_to_file(token: str) -> None:
    """Persist the bot token to the state file."""
    _STATE_FILE.write_text(json.dumps({"token": token}))


class TelegramBot:
    """Manages the lifecycle of the python-telegram-bot Application.

    Integrates with an existing asyncio event loop (e.g. FastAPI's).
    """

    def __init__(self) -> None:
        self._app = None
        self._token: str | None = None
        self._running: bool = False

    # ── Token helpers ─────────────────────────────────────────────────────────

    def load_token(self) -> str | None:
        """Return the token from the state file or TELEGRAM_TOKEN env var."""
        from_file = _load_token_from_file()
        if from_file:
            return from_file
        try:
            from config import settings
            return settings.telegram_token or None
        except Exception:
            return None

    def save_token(self, token: str) -> None:
        """Persist token so it survives restarts."""
        _save_token_to_file(token)

    # ── Status ────────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def token_set(self) -> bool:
        return bool(self._token)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, token: str | None = None) -> bool:
        """Start the bot.  Returns True on success, False otherwise."""
        if self._running:
            return True

        tok = token or self.load_token()
        if not tok:
            logger.warning("Telegram bot: no token configured, skipping start.")
            return False

        try:
            from telegram import Update
            from telegram.ext import (
                Application,
                CommandHandler,
                ContextTypes,
                MessageHandler,
                filters,
            )
        except ImportError:
            logger.error(
                "python-telegram-bot is not installed. "
                'Run: pip install ".[telegram]"'
            )
            return False

        try:
            self._token = tok
            self._app = Application.builder().token(tok).build()

            self._app.add_handler(CommandHandler("start", self._cmd_start))
            self._app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
            )

            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

            self._running = True
            logger.info("Telegram bot started.")
            return True

        except Exception as exc:
            logger.error("Telegram bot failed to start: %s", exc)
            self._running = False
            self._token = None
            self._app = None
            return False

    async def stop(self) -> None:
        """Gracefully shut down the bot."""
        if not self._running or self._app is None:
            return
        try:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped.")
        except Exception as exc:
            logger.error("Error stopping Telegram bot: %s", exc)
        finally:
            self._running = False

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _cmd_start(self, update, context) -> None:
        await update.message.reply_text(
            "Sir, affirmative. I'm Timmy — your sovereign local AI agent. "
            "Send me any message and I'll get right on it."
        )

    async def _handle_message(self, update, context) -> None:
        user_text = update.message.text
        try:
            from timmy.agent import create_timmy
            agent = create_timmy()
            run = await asyncio.to_thread(agent.run, user_text, stream=False)
            response = run.content if hasattr(run, "content") else str(run)
        except Exception as exc:
            logger.error("Timmy error in Telegram handler: %s", exc)
            response = f"Timmy is offline: {exc}"
        await update.message.reply_text(response)


# Module-level singleton
telegram_bot = TelegramBot()
