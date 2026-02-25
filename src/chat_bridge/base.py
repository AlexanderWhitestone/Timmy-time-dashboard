"""ChatPlatform — abstract base class for all chat vendor integrations.

Each vendor (Discord, Telegram, Slack, etc.) implements this interface.
The dashboard and agent code interact only with this contract, never
with vendor-specific APIs directly.

Architecture:
    ChatPlatform (ABC)
        |
        +-- DiscordVendor   (discord.py)
        +-- TelegramVendor  (future migration)
        +-- SlackVendor     (future)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional


class PlatformState(Enum):
    """Lifecycle state of a chat platform connection."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()


@dataclass
class ChatMessage:
    """Vendor-agnostic representation of a chat message."""
    content: str
    author: str
    channel_id: str
    platform: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    attachments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatThread:
    """Vendor-agnostic representation of a conversation thread."""
    thread_id: str
    title: str
    channel_id: str
    platform: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    archived: bool = False
    message_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InviteInfo:
    """Parsed invite extracted from an image or text."""
    url: str
    code: str
    platform: str
    guild_name: Optional[str] = None
    source: str = "unknown"  # "qr", "vision", "text"


@dataclass
class PlatformStatus:
    """Current status of a chat platform connection."""
    platform: str
    state: PlatformState
    token_set: bool
    guild_count: int = 0
    thread_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "state": self.state.name.lower(),
            "connected": self.state == PlatformState.CONNECTED,
            "token_set": self.token_set,
            "guild_count": self.guild_count,
            "thread_count": self.thread_count,
            "error": self.error,
        }


class ChatPlatform(ABC):
    """Abstract base class for chat platform integrations.

    Lifecycle:
        configure(token) -> start() -> [send/receive messages] -> stop()

    All vendors implement this interface. The dashboard routes and
    agent code work with ChatPlatform, never with vendor-specific APIs.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Platform identifier (e.g., 'discord', 'telegram')."""

    @property
    @abstractmethod
    def state(self) -> PlatformState:
        """Current connection state."""

    @abstractmethod
    async def start(self, token: Optional[str] = None) -> bool:
        """Start the platform connection. Returns True on success."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully disconnect."""

    @abstractmethod
    async def send_message(
        self, channel_id: str, content: str, thread_id: Optional[str] = None
    ) -> Optional[ChatMessage]:
        """Send a message. Optionally within a thread."""

    @abstractmethod
    async def create_thread(
        self, channel_id: str, title: str, initial_message: Optional[str] = None
    ) -> Optional[ChatThread]:
        """Create a new thread in a channel."""

    @abstractmethod
    async def join_from_invite(self, invite_code: str) -> bool:
        """Join a server/workspace using an invite code."""

    @abstractmethod
    def status(self) -> PlatformStatus:
        """Return current platform status."""

    @abstractmethod
    def save_token(self, token: str) -> None:
        """Persist token for restarts."""

    @abstractmethod
    def load_token(self) -> Optional[str]:
        """Load persisted token."""
