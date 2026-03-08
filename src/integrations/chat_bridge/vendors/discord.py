"""DiscordVendor — Discord integration via discord.py.

Implements ChatPlatform with native thread support.  Each conversation
with Timmy gets its own Discord thread, keeping channels clean.

Optional dependency — install with:
    pip install ".[discord]"

Architecture:
    DiscordVendor
        ├── _client (discord.Client)     — handles gateway events
        ├── _thread_map                  — channel_id -> active thread
        └── _message_handler             — bridges to Timmy agent
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from integrations.chat_bridge.base import (
    ChatMessage,
    ChatPlatform,
    ChatThread,
    InviteInfo,
    PlatformState,
    PlatformStatus,
)

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).parent.parent.parent.parent / "discord_state.json"

# Module-level agent singleton — reused across all Discord messages.
# Mirrors the pattern from timmy.session._agent.
_discord_agent = None


def _get_discord_agent():
    """Lazy-initialize the Discord agent singleton."""
    global _discord_agent
    if _discord_agent is None:
        from timmy.agent import create_timmy

        try:
            _discord_agent = create_timmy()
            logger.info("Discord: Timmy agent initialized (singleton)")
        except Exception as exc:
            logger.error("Discord: Failed to create Timmy agent: %s", exc)
            raise
    return _discord_agent


class DiscordVendor(ChatPlatform):
    """Discord integration with native thread conversations.

    Every user interaction creates or continues a Discord thread,
    keeping channel history clean and conversations organized.
    """

    def __init__(self) -> None:
        self._client = None
        self._token: Optional[str] = None
        self._state: PlatformState = PlatformState.DISCONNECTED
        self._task: Optional[asyncio.Task] = None
        self._guild_count: int = 0
        self._active_threads: dict[str, str] = {}  # channel_id -> thread_id

    # ── ChatPlatform interface ─────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "discord"

    @property
    def state(self) -> PlatformState:
        return self._state

    async def start(self, token: Optional[str] = None) -> bool:
        """Start the Discord bot. Returns True on success."""
        if self._state == PlatformState.CONNECTED:
            return True

        tok = token or self.load_token()
        if not tok:
            logger.warning("Discord bot: no token configured, skipping start.")
            return False

        try:
            import discord
        except ImportError:
            logger.error(
                "discord.py is not installed. "
                'Run: pip install ".[discord]"'
            )
            return False

        try:
            self._state = PlatformState.CONNECTING
            self._token = tok

            intents = discord.Intents.default()
            intents.message_content = True
            intents.guilds = True

            self._client = discord.Client(intents=intents)
            self._register_handlers()

            # Run the client in a background task so we don't block
            self._task = asyncio.create_task(self._run_client(tok))

            # Wait briefly for connection
            for _ in range(30):
                await asyncio.sleep(0.5)
                if self._state == PlatformState.CONNECTED:
                    logger.info("Discord bot connected (%d guilds).", self._guild_count)
                    return True
                if self._state == PlatformState.ERROR:
                    return False

            logger.warning("Discord bot: connection timed out.")
            self._state = PlatformState.ERROR
            return False

        except Exception as exc:
            logger.error("Discord bot failed to start: %s", exc)
            self._state = PlatformState.ERROR
            self._token = None
            self._client = None
            return False

    async def stop(self) -> None:
        """Gracefully disconnect the Discord bot."""
        if self._client and not self._client.is_closed():
            try:
                await self._client.close()
                logger.info("Discord bot disconnected.")
            except Exception as exc:
                logger.error("Error stopping Discord bot: %s", exc)

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._state = PlatformState.DISCONNECTED
        self._client = None
        self._task = None

    async def send_message(
        self, channel_id: str, content: str, thread_id: Optional[str] = None
    ) -> Optional[ChatMessage]:
        """Send a message to a Discord channel or thread."""
        if not self._client or self._state != PlatformState.CONNECTED:
            return None

        try:
            import discord

            target_id = int(thread_id) if thread_id else int(channel_id)
            channel = self._client.get_channel(target_id)

            if channel is None:
                channel = await self._client.fetch_channel(target_id)

            msg = await channel.send(content)

            return ChatMessage(
                content=content,
                author=str(self._client.user),
                channel_id=str(msg.channel.id),
                platform="discord",
                message_id=str(msg.id),
                thread_id=thread_id,
            )
        except Exception as exc:
            logger.error("Failed to send Discord message: %s", exc)
            return None

    async def create_thread(
        self, channel_id: str, title: str, initial_message: Optional[str] = None
    ) -> Optional[ChatThread]:
        """Create a new thread in a Discord channel."""
        if not self._client or self._state != PlatformState.CONNECTED:
            return None

        try:
            channel = self._client.get_channel(int(channel_id))
            if channel is None:
                channel = await self._client.fetch_channel(int(channel_id))

            thread = await channel.create_thread(
                name=title[:100],  # Discord limits thread names to 100 chars
                auto_archive_duration=1440,  # 24 hours
            )

            if initial_message:
                await thread.send(initial_message)

            self._active_threads[channel_id] = str(thread.id)

            return ChatThread(
                thread_id=str(thread.id),
                title=title[:100],
                channel_id=channel_id,
                platform="discord",
            )
        except Exception as exc:
            logger.error("Failed to create Discord thread: %s", exc)
            return None

    async def join_from_invite(self, invite_code: str) -> bool:
        """Join a Discord server using an invite code.

        Note: Bot accounts cannot use invite links directly.
        This generates an OAuth2 URL for adding the bot to a server.
        The invite_code is validated but the actual join requires
        the server admin to use the bot's OAuth2 authorization URL.
        """
        if not self._client or self._state != PlatformState.CONNECTED:
            logger.warning("Discord bot not connected, cannot process invite.")
            return False

        try:
            import discord

            invite = await self._client.fetch_invite(invite_code)
            logger.info(
                "Validated invite for server '%s' (code: %s)",
                invite.guild.name if invite.guild else "unknown",
                invite_code,
            )
            return True
        except Exception as exc:
            logger.error("Invalid Discord invite '%s': %s", invite_code, exc)
            return False

    def status(self) -> PlatformStatus:
        return PlatformStatus(
            platform="discord",
            state=self._state,
            token_set=bool(self._token),
            guild_count=self._guild_count,
            thread_count=len(self._active_threads),
        )

    def save_token(self, token: str) -> None:
        """Persist token to state file."""
        try:
            _STATE_FILE.write_text(json.dumps({"token": token}))
        except Exception as exc:
            logger.error("Failed to save Discord token: %s", exc)

    def load_token(self) -> Optional[str]:
        """Load token from state file or config."""
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text())
                token = data.get("token")
                if token:
                    return token
        except Exception as exc:
            logger.debug("Could not read discord state file: %s", exc)

        try:
            from config import settings
            return settings.discord_token or None
        except Exception:
            return None

    # ── OAuth2 URL generation ──────────────────────────────────────────────

    def get_oauth2_url(self) -> Optional[str]:
        """Generate the OAuth2 URL for adding this bot to a server.

        Requires the bot to be connected to read its application ID.
        """
        if not self._client or not self._client.user:
            return None

        app_id = self._client.user.id
        # Permissions: Send Messages, Create Public Threads, Manage Threads,
        # Read Message History, Embed Links, Attach Files
        permissions = 397284550656
        return (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={app_id}&scope=bot"
            f"&permissions={permissions}"
        )

    # ── Internal ───────────────────────────────────────────────────────────

    async def _run_client(self, token: str) -> None:
        """Run the discord.py client (blocking call in a task)."""
        try:
            await self._client.start(token)
        except Exception as exc:
            logger.error("Discord client error: %s", exc)
            self._state = PlatformState.ERROR

    def _register_handlers(self) -> None:
        """Register Discord event handlers on the client."""

        @self._client.event
        async def on_ready():
            self._guild_count = len(self._client.guilds)
            self._state = PlatformState.CONNECTED
            logger.info(
                "Discord ready: %s in %d guild(s)",
                self._client.user,
                self._guild_count,
            )

        @self._client.event
        async def on_message(message):
            # Ignore our own messages
            if message.author == self._client.user:
                return

            # Only respond to mentions or DMs
            is_dm = not hasattr(message.channel, "guild") or message.channel.guild is None
            is_mention = self._client.user in message.mentions

            if not is_dm and not is_mention:
                return

            await self._handle_message(message)

        @self._client.event
        async def on_disconnect():
            if self._state != PlatformState.DISCONNECTED:
                self._state = PlatformState.CONNECTING
                logger.warning("Discord disconnected, will auto-reconnect.")

    async def _handle_message(self, message) -> None:
        """Process an incoming message and respond via a thread."""
        # Strip the bot mention from the message content
        content = message.content
        if self._client.user:
            content = content.replace(f"<@{self._client.user.id}>", "").strip()

        if not content:
            return

        # Create or reuse a thread for this conversation
        thread = await self._get_or_create_thread(message)
        target = thread or message.channel

        # Derive session_id for per-conversation history via Agno's SQLite
        if thread:
            session_id = f"discord_{thread.id}"
        else:
            session_id = f"discord_{message.channel.id}"

        # Run Timmy agent (singleton, with session continuity)
        try:
            agent = _get_discord_agent()
            run = await asyncio.to_thread(
                agent.run, content, stream=False, session_id=session_id
            )
            response = run.content if hasattr(run, "content") else str(run)
        except Exception as exc:
            logger.error("Timmy error in Discord handler: %s", exc)
            response = f"Timmy is offline: {exc}"

        # Strip hallucinated tool-call JSON and chain-of-thought narration
        from timmy.session import _clean_response

        response = _clean_response(response)

        # Discord has a 2000 character limit
        for chunk in _chunk_message(response, 2000):
            await target.send(chunk)

    async def _get_or_create_thread(self, message):
        """Get the active thread for a channel, or create one.

        If the message is already in a thread, use that thread.
        Otherwise, create a new thread from the message.
        """
        try:
            import discord

            # Already in a thread — just use it
            if isinstance(message.channel, discord.Thread):
                return message.channel

            # DM channels don't support threads
            if isinstance(message.channel, discord.DMChannel):
                return None

            # Create a thread from this message
            from config import settings
            thread_name = f"{settings.agent_name} | {message.author.display_name}"
            thread = await message.create_thread(
                name=thread_name[:100],
                auto_archive_duration=1440,
            )
            channel_id = str(message.channel.id)
            self._active_threads[channel_id] = str(thread.id)
            return thread

        except Exception as exc:
            logger.debug("Could not create thread: %s", exc)
            return None


def _chunk_message(text: str, max_len: int = 2000) -> list[str]:
    """Split a message into chunks that fit Discord's character limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at a newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# Module-level singleton
discord_bot = DiscordVendor()
