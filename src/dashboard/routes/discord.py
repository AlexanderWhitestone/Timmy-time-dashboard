"""Dashboard routes for Discord bot setup, status, and invite-from-image.

Endpoints:
    POST /discord/setup      — configure bot token
    GET  /discord/status     — connection state + guild count
    POST /discord/join       — paste screenshot → extract invite → join
    GET  /discord/oauth-url  — get the bot's OAuth2 authorization URL
"""

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/discord", tags=["discord"])


class TokenPayload(BaseModel):
    token: str


@router.post("/setup")
async def setup_discord(payload: TokenPayload):
    """Configure the Discord bot token and (re)start the bot.

    Send POST with JSON body: {"token": "<your-bot-token>"}
    Get the token from https://discord.com/developers/applications
    """
    from chat_bridge.vendors.discord import discord_bot

    token = payload.token.strip()
    if not token:
        return {"ok": False, "error": "Token cannot be empty."}

    discord_bot.save_token(token)

    if discord_bot.state.name == "CONNECTED":
        await discord_bot.stop()

    success = await discord_bot.start(token=token)
    if success:
        return {"ok": True, "message": "Discord bot connected successfully."}
    return {
        "ok": False,
        "error": (
            "Failed to start bot. Check that the token is correct and "
            'discord.py is installed: pip install ".[discord]"'
        ),
    }


@router.get("/status")
async def discord_status():
    """Return current Discord bot status."""
    from chat_bridge.vendors.discord import discord_bot

    return discord_bot.status().to_dict()


@router.post("/join")
async def join_from_image(
    image: Optional[UploadFile] = File(None),
    invite_url: Optional[str] = Form(None),
):
    """Extract a Discord invite from a screenshot or text and validate it.

    Accepts either:
        - An uploaded image (screenshot of invite or QR code)
        - A plain text invite URL

    The bot validates the invite and returns the OAuth2 URL for the
    server admin to authorize the bot.
    """
    from chat_bridge.invite_parser import invite_parser
    from chat_bridge.vendors.discord import discord_bot

    invite_info = None

    # Try image first
    if image and image.filename:
        image_data = await image.read()
        if image_data:
            invite_info = await invite_parser.parse_image(image_data)

    # Fall back to text
    if not invite_info and invite_url:
        invite_info = invite_parser.parse_text(invite_url)

    if not invite_info:
        return {
            "ok": False,
            "error": (
                "No Discord invite found. "
                "Paste a screenshot with a visible invite link or QR code, "
                "or enter the invite URL directly."
            ),
        }

    # Validate the invite
    valid = await discord_bot.join_from_invite(invite_info.code)

    result = {
        "ok": True,
        "invite": {
            "code": invite_info.code,
            "url": invite_info.url,
            "source": invite_info.source,
            "platform": invite_info.platform,
        },
        "validated": valid,
    }

    # Include OAuth2 URL if bot is connected
    oauth_url = discord_bot.get_oauth2_url()
    if oauth_url:
        result["oauth2_url"] = oauth_url
        result["message"] = (
            "Invite validated. Share this OAuth2 URL with the server admin "
            "to add Timmy to the server."
        )
    else:
        result["message"] = (
            "Invite found but bot is not connected. "
            "Configure a bot token first via /discord/setup."
        )

    return result


@router.get("/oauth-url")
async def discord_oauth_url():
    """Get the bot's OAuth2 authorization URL for adding to servers."""
    from chat_bridge.vendors.discord import discord_bot

    url = discord_bot.get_oauth2_url()
    if url:
        return {"ok": True, "url": url}
    return {
        "ok": False,
        "error": "Bot is not connected. Configure a token first.",
    }
