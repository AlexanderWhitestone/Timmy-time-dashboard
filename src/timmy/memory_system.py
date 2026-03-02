"""Unified memory system for Timmy.

Architecture:
- Single SQLite database via brain.memory.UnifiedMemory
- Hot memory, vault notes, handoff, facts, and semantic search
  all live in the same database.

The MemorySystem class provides the same public API as before,
but delegates everything to UnifiedMemory instead of parsing
markdown files and directories.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from brain.memory import UnifiedMemory, get_memory

logger = logging.getLogger(__name__)


class MemorySystem:
    """Central memory system backed by UnifiedMemory (SQLite).

    Public API is unchanged from the original three-tier system.
    Internally, everything goes through brain.memory.UnifiedMemory.
    """

    def __init__(self) -> None:
        self._memory: Optional[UnifiedMemory] = None
        self.session_start_time: Optional[datetime] = None
        self.session_decisions: list[str] = []
        self.session_open_items: list[str] = []

    @property
    def memory(self) -> UnifiedMemory:
        """Lazy-load the UnifiedMemory singleton."""
        if self._memory is None:
            self._memory = get_memory(source="timmy")
        return self._memory

    def start_session(self) -> str:
        """Start a new session, loading context from memory."""
        self.session_start_time = datetime.now(timezone.utc)
        context_parts = []

        # 1. Hot memory
        hot_formatted = self.memory.get_hot_memory_formatted()
        if hot_formatted:
            context_parts.append("## Hot Memory\n" + hot_formatted)

        # 2. Last session handoff
        handoff = self.memory.read_handoff()
        if handoff:
            context_parts.append(
                f"## Previous Session\n\n{handoff['summary']}"
            )
            self.memory.clear_handoff()

        # 3. User facts
        facts = self.memory.get_facts_sync(category="user_preference", limit=5)
        if facts:
            lines = ["## User Context"]
            for f in facts:
                lines.append(f"- {f['content']}")
            context_parts.append("\n".join(lines))

        full_context = "\n\n---\n\n".join(context_parts)
        logger.info("MemorySystem: Session started with %d chars context", len(full_context))
        return full_context

    def end_session(self, summary: str) -> None:
        """End session, write handoff."""
        self.memory.write_handoff(
            session_summary=summary,
            key_decisions=self.session_decisions,
            open_items=self.session_open_items,
        )

        # Update hot memory
        self.memory.update_hot_section(
            "Current Session",
            f"**Last Session:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
            f"**Summary:** {summary[:100]}...",
        )

        logger.info("MemorySystem: Session ended, handoff written")

    def record_decision(self, decision: str) -> None:
        """Record a key decision during session."""
        self.session_decisions.append(decision)

    def record_open_item(self, item: str) -> None:
        """Record an open item for follow-up."""
        self.session_open_items.append(item)

    def update_user_fact(self, key: str, value: str) -> None:
        """Update user profile fact in unified memory."""
        self.memory.store_fact_sync(
            category="user_preference",
            content=f"{key}: {value}",
            confidence=0.9,
            source="user",
        )
        # Also update hot memory for quick access
        if key.lower() == "name":
            self.memory.update_hot_section("User Profile", f"**Name:** {value}")

    def get_system_context(self) -> str:
        """Get full context for system prompt injection."""
        return self.start_session()


# Module-level singleton
memory_system = MemorySystem()
