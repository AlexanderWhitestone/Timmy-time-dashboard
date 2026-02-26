"""PlatformRegistry — singleton registry for chat platform vendors.

Provides a central point for registering, discovering, and managing
all chat platform integrations. Dashboard routes and the agent core
interact with platforms through this registry.

Usage:
    from integrations.chat_bridge.registry import platform_registry

    platform_registry.register(discord_vendor)
    discord = platform_registry.get("discord")
    all_platforms = platform_registry.list_platforms()
"""

import logging
from typing import Optional

from integrations.chat_bridge.base import ChatPlatform, PlatformStatus

logger = logging.getLogger(__name__)


class PlatformRegistry:
    """Thread-safe registry of ChatPlatform vendors."""

    def __init__(self) -> None:
        self._platforms: dict[str, ChatPlatform] = {}

    def register(self, platform: ChatPlatform) -> None:
        """Register a chat platform vendor."""
        name = platform.name
        if name in self._platforms:
            logger.warning("Platform '%s' already registered, replacing.", name)
        self._platforms[name] = platform
        logger.info("Registered chat platform: %s", name)

    def unregister(self, name: str) -> bool:
        """Remove a platform from the registry. Returns True if it existed."""
        if name in self._platforms:
            del self._platforms[name]
            logger.info("Unregistered chat platform: %s", name)
            return True
        return False

    def get(self, name: str) -> Optional[ChatPlatform]:
        """Get a platform by name."""
        return self._platforms.get(name)

    def list_platforms(self) -> list[PlatformStatus]:
        """Return status of all registered platforms."""
        return [p.status() for p in self._platforms.values()]

    async def start_all(self) -> dict[str, bool]:
        """Start all registered platforms. Returns name -> success mapping."""
        results = {}
        for name, platform in self._platforms.items():
            try:
                results[name] = await platform.start()
            except Exception as exc:
                logger.error("Failed to start platform '%s': %s", name, exc)
                results[name] = False
        return results

    async def stop_all(self) -> None:
        """Stop all registered platforms."""
        for name, platform in self._platforms.items():
            try:
                await platform.stop()
            except Exception as exc:
                logger.error("Error stopping platform '%s': %s", name, exc)


# Module-level singleton
platform_registry = PlatformRegistry()
