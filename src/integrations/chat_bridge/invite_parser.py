"""InviteParser — extract chat platform invite links from images.

Strategy chain:
    1. QR code detection (pyzbar — fast, no GPU)
    2. Ollama vision OCR (local LLM — handles screenshots with visible URLs)
    3. Regex fallback on raw text input

Supports Discord invite patterns:
    - discord.gg/<code>
    - discord.com/invite/<code>
    - discordapp.com/invite/<code>

Usage:
    from integrations.chat_bridge.invite_parser import invite_parser

    # From image bytes (screenshot or QR photo)
    result = await invite_parser.parse_image(image_bytes)

    # From plain text
    result = invite_parser.parse_text("Join us at discord.gg/abc123")
"""

import io
import logging
import re
from typing import Optional

from integrations.chat_bridge.base import InviteInfo

logger = logging.getLogger(__name__)

# Patterns for Discord invite URLs
_DISCORD_PATTERNS = [
    re.compile(r"(?:https?://)?discord\.gg/([A-Za-z0-9\-_]+)"),
    re.compile(r"(?:https?://)?(?:www\.)?discord(?:app)?\.com/invite/([A-Za-z0-9\-_]+)"),
]


def _extract_discord_code(text: str) -> Optional[str]:
    """Extract a Discord invite code from text."""
    for pattern in _DISCORD_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


class InviteParser:
    """Multi-strategy invite parser.

    Tries QR detection first (fast), then Ollama vision (local AI),
    then regex on raw text. All local, no cloud.
    """

    async def parse_image(self, image_data: bytes) -> Optional[InviteInfo]:
        """Extract an invite from image bytes (screenshot or QR photo).

        Tries strategies in order:
            1. QR code decode (pyzbar)
            2. Ollama vision model (local OCR)
        """
        result = self._try_qr_decode(image_data)
        if result:
            return result

        result = await self._try_ollama_vision(image_data)
        if result:
            return result

        logger.info("No invite found in image via any strategy.")
        return None

    def parse_text(self, text: str) -> Optional[InviteInfo]:
        """Extract an invite from plain text."""
        code = _extract_discord_code(text)
        if code:
            return InviteInfo(
                url=f"https://discord.gg/{code}",
                code=code,
                platform="discord",
                source="text",
            )
        return None

    def _try_qr_decode(self, image_data: bytes) -> Optional[InviteInfo]:
        """Strategy 1: Decode QR codes from image using pyzbar."""
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode as qr_decode
        except ImportError:
            logger.debug("pyzbar/Pillow not installed, skipping QR strategy.")
            return None

        try:
            image = Image.open(io.BytesIO(image_data))
            decoded = qr_decode(image)

            for obj in decoded:
                text = obj.data.decode("utf-8", errors="ignore")
                code = _extract_discord_code(text)
                if code:
                    logger.info("QR decode found Discord invite: %s", code)
                    return InviteInfo(
                        url=f"https://discord.gg/{code}",
                        code=code,
                        platform="discord",
                        source="qr",
                    )
        except Exception as exc:
            logger.debug("QR decode failed: %s", exc)

        return None

    async def _try_ollama_vision(self, image_data: bytes) -> Optional[InviteInfo]:
        """Strategy 2: Use Ollama vision model for local OCR."""
        try:
            import base64
            import httpx
            from config import settings
        except ImportError:
            logger.debug("httpx not available for Ollama vision.")
            return None

        try:
            b64_image = base64.b64encode(image_data).decode("ascii")

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.ollama_model,
                        "prompt": (
                            "Extract any Discord invite link from this image. "
                            "Look for URLs like discord.gg/CODE or "
                            "discord.com/invite/CODE. "
                            "Reply with ONLY the invite URL, nothing else. "
                            "If no invite link is found, reply with: NONE"
                        ),
                        "images": [b64_image],
                        "stream": False,
                    },
                )

            if resp.status_code != 200:
                logger.debug("Ollama vision returned %d", resp.status_code)
                return None

            answer = resp.json().get("response", "").strip()
            if answer and answer.upper() != "NONE":
                code = _extract_discord_code(answer)
                if code:
                    logger.info("Ollama vision found Discord invite: %s", code)
                    return InviteInfo(
                        url=f"https://discord.gg/{code}",
                        code=code,
                        platform="discord",
                        source="vision",
                    )
        except Exception as exc:
            logger.debug("Ollama vision strategy failed: %s", exc)

        return None


# Module-level singleton
invite_parser = InviteParser()
