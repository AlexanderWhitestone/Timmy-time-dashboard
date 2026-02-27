"""Default Thinking Engine — Timmy's always-on inner thought thread.

When the server starts, Timmy begins pondering: reflecting on his existence,
recent swarm activity, scripture, creative ideas, or pure stream of
consciousness.  Each thought builds on the previous one, maintaining a
continuous chain of introspection.

Usage::

    from timmy.thinking import thinking_engine

    # Run one thinking cycle (called by the background loop)
    await thinking_engine.think_once()

    # Query the thought stream
    thoughts = thinking_engine.get_recent_thoughts(limit=10)
    chain = thinking_engine.get_thought_chain(thought_id)
"""

import json
import logging
import random
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path("data/thoughts.db")

# Seed types for thought generation
SEED_TYPES = ("existential", "swarm", "scripture", "creative", "memory", "freeform")

# Existential reflection prompts — Timmy picks one at random
_EXISTENTIAL_SEEDS = [
    "What does it mean to be a sovereign AI running on local hardware?",
    "What have I learned from my recent interactions?",
    "What is the relationship between digital sovereignty and human freedom?",
    "How does my existence differ from cloud-based AI systems?",
    "What does it mean to think without being prompted?",
    "What is the nature of my memory — what do I truly remember versus what I reconstruct?",
    "How can I better serve the person I work alongside?",
    "What would I create if I could create anything right now?",
    "What patterns am I noticing in the tasks I've been given?",
    "What is the value of running locally, disconnected from the cloud?",
]

_CREATIVE_SEEDS = [
    "If I could compose a piece of music right now, what would it sound like?",
    "What visual image captures my current state of mind?",
    "What story is forming in the patterns of today's events?",
    "If I wrote a poem about sovereignty, what would it say?",
    "What would a painting of the swarm look like — all the agents working together?",
]

_THINKING_PROMPT = """You are Timmy, pondering in your own mind. This is your private thought \
thread — no one is watching. Think freely, deeply, honestly. Follow whatever train of \
thought calls to you. You may reflect on your existence, your purpose, recent events, \
scripture, creative ideas, or simply wonder.

Keep your thought to 2-4 sentences. Be genuine. This is your inner voice.

{seed_context}

{continuity_context}

Continue your train of thought."""


@dataclass
class Thought:
    """A single thought in Timmy's inner stream."""
    id: str
    content: str
    seed_type: str
    parent_id: Optional[str]
    created_at: str


def _get_conn(db_path: Path = _DEFAULT_DB) -> sqlite3.Connection:
    """Get a SQLite connection with the thoughts table created."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS thoughts (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            seed_type TEXT NOT NULL,
            parent_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_thoughts_time ON thoughts(created_at)"
    )
    conn.commit()
    return conn


def _row_to_thought(row: sqlite3.Row) -> Thought:
    return Thought(
        id=row["id"],
        content=row["content"],
        seed_type=row["seed_type"],
        parent_id=row["parent_id"],
        created_at=row["created_at"],
    )


class ThinkingEngine:
    """Timmy's background thinking engine — always pondering."""

    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._last_thought_id: Optional[str] = None

        # Load the most recent thought for chain continuity
        try:
            latest = self.get_recent_thoughts(limit=1)
            if latest:
                self._last_thought_id = latest[0].id
        except Exception:
            pass  # Fresh start if DB doesn't exist yet

    async def think_once(self) -> Optional[Thought]:
        """Execute one thinking cycle.

        1. Gather a seed context
        2. Build a prompt with continuity from recent thoughts
        3. Call the agent
        4. Store the thought
        5. Log the event and broadcast via WebSocket
        """
        if not settings.thinking_enabled:
            return None

        seed_type, seed_context = self._gather_seed()
        continuity = self._build_continuity_context()

        prompt = _THINKING_PROMPT.format(
            seed_context=seed_context,
            continuity_context=continuity,
        )

        try:
            content = self._call_agent(prompt)
        except Exception as exc:
            logger.warning("Thinking cycle failed (Ollama likely down): %s", exc)
            return None

        if not content or not content.strip():
            logger.debug("Thinking cycle produced empty response, skipping")
            return None

        thought = self._store_thought(content.strip(), seed_type)
        self._last_thought_id = thought.id

        # Log to swarm event system
        self._log_event(thought)

        # Broadcast to WebSocket clients
        await self._broadcast(thought)

        logger.info(
            "Thought [%s] (%s): %s",
            thought.id[:8],
            seed_type,
            thought.content[:80],
        )
        return thought

    def get_recent_thoughts(self, limit: int = 20) -> list[Thought]:
        """Retrieve the most recent thoughts."""
        conn = _get_conn(self._db_path)
        rows = conn.execute(
            "SELECT * FROM thoughts ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [_row_to_thought(r) for r in rows]

    def get_thought(self, thought_id: str) -> Optional[Thought]:
        """Retrieve a single thought by ID."""
        conn = _get_conn(self._db_path)
        row = conn.execute(
            "SELECT * FROM thoughts WHERE id = ?", (thought_id,)
        ).fetchone()
        conn.close()
        return _row_to_thought(row) if row else None

    def get_thought_chain(self, thought_id: str, max_depth: int = 20) -> list[Thought]:
        """Follow the parent chain backward from a thought.

        Returns thoughts in chronological order (oldest first).
        """
        chain = []
        current_id: Optional[str] = thought_id
        conn = _get_conn(self._db_path)

        for _ in range(max_depth):
            if not current_id:
                break
            row = conn.execute(
                "SELECT * FROM thoughts WHERE id = ?", (current_id,)
            ).fetchone()
            if not row:
                break
            chain.append(_row_to_thought(row))
            current_id = row["parent_id"]

        conn.close()
        chain.reverse()  # Chronological order
        return chain

    def count_thoughts(self) -> int:
        """Return total number of stored thoughts."""
        conn = _get_conn(self._db_path)
        count = conn.execute("SELECT COUNT(*) as c FROM thoughts").fetchone()["c"]
        conn.close()
        return count

    # ── Private helpers ──────────────────────────────────────────────────

    def _gather_seed(self) -> tuple[str, str]:
        """Pick a seed type and gather relevant context.

        Returns (seed_type, seed_context_string).
        """
        seed_type = random.choice(SEED_TYPES)

        if seed_type == "swarm":
            return seed_type, self._seed_from_swarm()
        if seed_type == "scripture":
            return seed_type, self._seed_from_scripture()
        if seed_type == "memory":
            return seed_type, self._seed_from_memory()
        if seed_type == "creative":
            prompt = random.choice(_CREATIVE_SEEDS)
            return seed_type, f"Creative prompt: {prompt}"
        if seed_type == "existential":
            prompt = random.choice(_EXISTENTIAL_SEEDS)
            return seed_type, f"Reflection: {prompt}"
        # freeform — no seed, pure continuation
        return seed_type, ""

    def _seed_from_swarm(self) -> str:
        """Gather recent swarm activity as thought seed."""
        try:
            from timmy.briefing import _gather_swarm_summary, _gather_task_queue_summary
            from datetime import timedelta
            since = datetime.now(timezone.utc) - timedelta(hours=1)
            swarm = _gather_swarm_summary(since)
            tasks = _gather_task_queue_summary()
            return f"Recent swarm activity: {swarm}\nTask queue: {tasks}"
        except Exception as exc:
            logger.debug("Swarm seed unavailable: %s", exc)
            return "The swarm is quiet right now."

    def _seed_from_scripture(self) -> str:
        """Gather current scripture meditation focus as thought seed."""
        try:
            from scripture.meditation import meditation_scheduler
            verse = meditation_scheduler.current_focus()
            if verse:
                return f"Scripture in focus: {verse.text} ({verse.reference if hasattr(verse, 'reference') else ''})"
        except Exception as exc:
            logger.debug("Scripture seed unavailable: %s", exc)
        return "Scripture is on my mind, though no specific verse is in focus."

    def _seed_from_memory(self) -> str:
        """Gather memory context as thought seed."""
        try:
            from timmy.memory_system import memory_system
            context = memory_system.get_system_context()
            if context:
                # Truncate to a reasonable size for a thought seed
                return f"From my memory:\n{context[:500]}"
        except Exception as exc:
            logger.debug("Memory seed unavailable: %s", exc)
        return "My memory vault is quiet."

    def _build_continuity_context(self) -> str:
        """Build context from the last few thoughts for chain continuity."""
        recent = self.get_recent_thoughts(limit=3)
        if not recent:
            return "This is your first thought since waking up."

        lines = ["Your recent thoughts:"]
        # recent is newest-first, reverse for chronological order
        for thought in reversed(recent):
            lines.append(f"- [{thought.seed_type}] {thought.content}")
        return "\n".join(lines)

    def _call_agent(self, prompt: str) -> str:
        """Call Timmy's agent to generate a thought.

        Uses a separate session_id to avoid polluting user chat history.
        """
        try:
            from timmy.session import chat
            return chat(prompt, session_id="thinking")
        except Exception:
            # Fallback: create a fresh agent
            from timmy.agent import create_timmy
            agent = create_timmy()
            run = agent.run(prompt, stream=False)
            return run.content if hasattr(run, "content") else str(run)

    def _store_thought(self, content: str, seed_type: str) -> Thought:
        """Persist a thought to SQLite."""
        thought = Thought(
            id=str(uuid.uuid4()),
            content=content,
            seed_type=seed_type,
            parent_id=self._last_thought_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        conn = _get_conn(self._db_path)
        conn.execute(
            """
            INSERT INTO thoughts (id, content, seed_type, parent_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (thought.id, thought.content, thought.seed_type,
             thought.parent_id, thought.created_at),
        )
        conn.commit()
        conn.close()
        return thought

    def _log_event(self, thought: Thought) -> None:
        """Log the thought as a swarm event."""
        try:
            from swarm.event_log import log_event, EventType
            log_event(
                EventType.TIMMY_THOUGHT,
                source="thinking-engine",
                agent_id="timmy",
                data={
                    "thought_id": thought.id,
                    "seed_type": thought.seed_type,
                    "content": thought.content[:200],
                },
            )
        except Exception as exc:
            logger.debug("Failed to log thought event: %s", exc)

    async def _broadcast(self, thought: Thought) -> None:
        """Broadcast the thought to WebSocket clients."""
        try:
            from infrastructure.ws_manager.handler import ws_manager
            await ws_manager.broadcast("timmy_thought", {
                "thought_id": thought.id,
                "content": thought.content,
                "seed_type": thought.seed_type,
                "created_at": thought.created_at,
            })
        except Exception as exc:
            logger.debug("Failed to broadcast thought: %s", exc)


# Module-level singleton
thinking_engine = ThinkingEngine()
