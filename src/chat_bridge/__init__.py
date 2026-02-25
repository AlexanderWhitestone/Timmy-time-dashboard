"""Chat Bridge — vendor-agnostic chat platform abstraction.

Provides a clean interface for integrating any chat platform
(Discord, Telegram, Slack, etc.) with Timmy's agent core.

Usage:
    from chat_bridge.base import ChatPlatform
    from chat_bridge.registry import platform_registry
    from chat_bridge.vendors.discord import DiscordVendor
"""
