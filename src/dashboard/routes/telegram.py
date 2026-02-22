"""Dashboard routes for Telegram bot setup and status."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/telegram", tags=["telegram"])


class TokenPayload(BaseModel):
    token: str


@router.post("/setup")
async def setup_telegram(payload: TokenPayload):
    """Accept a Telegram bot token, save it, and (re)start the bot.

    Send a POST with JSON body: {"token": "<your-bot-token>"}
    Get the token from @BotFather on Telegram.
    """
    from telegram_bot.bot import telegram_bot

    token = payload.token.strip()
    if not token:
        return {"ok": False, "error": "Token cannot be empty."}

    telegram_bot.save_token(token)

    if telegram_bot.is_running:
        await telegram_bot.stop()

    success = await telegram_bot.start(token=token)
    if success:
        return {"ok": True, "message": "Telegram bot started successfully."}
    return {
        "ok": False,
        "error": (
            "Failed to start bot. Check the token is correct and that "
            'python-telegram-bot is installed: pip install ".[telegram]"'
        ),
    }


@router.get("/status")
async def telegram_status():
    """Return the current state of the Telegram bot."""
    from telegram_bot.bot import telegram_bot

    return {
        "running": telegram_bot.is_running,
        "token_set": telegram_bot.token_set,
    }
