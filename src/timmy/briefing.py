"""Morning Briefing Engine — Timmy shows up before you ask.

BriefingEngine queries recent swarm activity and chat history, asks Timmy's
Agno agent to summarise the period, and returns a Briefing with an embedded
list of ApprovalItems the owner needs to action.

Briefings are cached in SQLite so page loads are instant.  A background task
regenerates the briefing every 6 hours.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".timmy" / "briefings.db"
_CACHE_MINUTES = 30


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ApprovalItem:
    """Lightweight representation used inside a Briefing.

    The canonical mutable version (with persistence) lives in timmy.approvals.
    This one travels with the Briefing dataclass as a read-only snapshot.
    """
    id: str
    title: str
    description: str
    proposed_action: str
    impact: str
    created_at: datetime
    status: str


@dataclass
class Briefing:
    generated_at: datetime
    summary: str                           # 150-300 words
    approval_items: list[ApprovalItem] = field(default_factory=list)
    period_start: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) - timedelta(hours=6)
    )
    period_end: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# SQLite cache
# ---------------------------------------------------------------------------

def _get_cache_conn(db_path: Path = _DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS briefings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end   TEXT NOT NULL,
            summary      TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _save_briefing(briefing: Briefing, db_path: Path = _DEFAULT_DB) -> None:
    conn = _get_cache_conn(db_path)
    conn.execute(
        """
        INSERT INTO briefings (generated_at, period_start, period_end, summary)
        VALUES (?, ?, ?, ?)
        """,
        (
            briefing.generated_at.isoformat(),
            briefing.period_start.isoformat(),
            briefing.period_end.isoformat(),
            briefing.summary,
        ),
    )
    conn.commit()
    conn.close()


def _load_latest(db_path: Path = _DEFAULT_DB) -> Optional[Briefing]:
    """Load the most-recently cached briefing, or None if there is none."""
    conn = _get_cache_conn(db_path)
    row = conn.execute(
        "SELECT * FROM briefings ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return Briefing(
        generated_at=datetime.fromisoformat(row["generated_at"]),
        period_start=datetime.fromisoformat(row["period_start"]),
        period_end=datetime.fromisoformat(row["period_end"]),
        summary=row["summary"],
    )


def is_fresh(briefing: Briefing, max_age_minutes: int = _CACHE_MINUTES) -> bool:
    """Return True if the briefing was generated within max_age_minutes."""
    now = datetime.now(timezone.utc)
    age = now - briefing.generated_at.replace(tzinfo=timezone.utc) if briefing.generated_at.tzinfo is None else now - briefing.generated_at
    return age.total_seconds() < max_age_minutes * 60


# ---------------------------------------------------------------------------
# Activity gathering helpers
# ---------------------------------------------------------------------------

def _gather_swarm_summary(since: datetime) -> str:
    """Pull recent task/agent stats from swarm.db.  Graceful if DB missing."""
    swarm_db = Path("data/swarm.db")
    if not swarm_db.exists():
        return "No swarm activity recorded yet."

    try:
        conn = sqlite3.connect(str(swarm_db))
        conn.row_factory = sqlite3.Row

        since_iso = since.isoformat()

        completed = conn.execute(
            "SELECT COUNT(*) as c FROM tasks WHERE status = 'completed' AND created_at > ?",
            (since_iso,),
        ).fetchone()["c"]

        failed = conn.execute(
            "SELECT COUNT(*) as c FROM tasks WHERE status = 'failed' AND created_at > ?",
            (since_iso,),
        ).fetchone()["c"]

        agents = conn.execute(
            "SELECT COUNT(*) as c FROM agents WHERE registered_at > ?",
            (since_iso,),
        ).fetchone()["c"]

        conn.close()

        parts = []
        if completed:
            parts.append(f"{completed} task(s) completed")
        if failed:
            parts.append(f"{failed} task(s) failed")
        if agents:
            parts.append(f"{agents} new agent(s) joined the swarm")

        return "; ".join(parts) if parts else "No swarm activity in this period."
    except Exception as exc:
        logger.debug("Swarm summary error: %s", exc)
        return "Swarm data unavailable."


def _gather_task_queue_summary() -> str:
    """Pull task queue stats for the briefing.  Graceful if unavailable."""
    try:
        from swarm.task_queue.models import get_task_summary_for_briefing
        stats = get_task_summary_for_briefing()
        parts = []
        if stats["pending_approval"]:
            parts.append(f"{stats['pending_approval']} task(s) pending approval")
        if stats["running"]:
            parts.append(f"{stats['running']} task(s) running")
        if stats["completed"]:
            parts.append(f"{stats['completed']} task(s) completed")
        if stats["failed"]:
            parts.append(f"{stats['failed']} task(s) failed")
            for fail in stats.get("recent_failures", []):
                parts.append(f"  - Failed: {fail['title']}")
        if stats["vetoed"]:
            parts.append(f"{stats['vetoed']} task(s) vetoed")
        return "; ".join(parts) if parts else "No tasks in the queue."
    except Exception as exc:
        logger.debug("Task queue summary error: %s", exc)
        return "Task queue data unavailable."


def _gather_chat_summary(since: datetime) -> str:
    """Pull recent chat messages from the in-memory log."""
    try:
        from dashboard.store import message_log
        messages = message_log.all()
        # Filter to messages in the briefing window (best-effort: no timestamps)
        recent = messages[-10:] if len(messages) > 10 else messages
        if not recent:
            return "No recent conversations."
        lines = []
        for msg in recent:
            role = "Owner" if msg.role == "user" else "Timmy"
            lines.append(f"{role}: {msg.content[:120]}")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Chat summary error: %s", exc)
        return "No recent conversations."


# ---------------------------------------------------------------------------
# BriefingEngine
# ---------------------------------------------------------------------------

class BriefingEngine:
    """Generates morning briefings by querying activity and asking Timmy."""

    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self._db_path = db_path

    def get_cached(self) -> Optional[Briefing]:
        """Return the cached briefing if it exists, without regenerating."""
        return _load_latest(self._db_path)

    def needs_refresh(self) -> bool:
        """True if there is no fresh briefing cached."""
        cached = _load_latest(self._db_path)
        if cached is None:
            return True
        return not is_fresh(cached)

    def generate(self) -> Briefing:
        """Generate a fresh briefing.  May take a few seconds (LLM call)."""
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(hours=6)

        swarm_info = _gather_swarm_summary(period_start)
        chat_info = _gather_chat_summary(period_start)
        task_info = _gather_task_queue_summary()

        prompt = (
            "You are Timmy, a sovereign local AI companion.\n"
            "Here is what happened since the last briefing:\n\n"
            f"SWARM ACTIVITY:\n{swarm_info}\n\n"
            f"TASK QUEUE:\n{task_info}\n\n"
            f"RECENT CONVERSATIONS:\n{chat_info}\n\n"
            "Summarize the last period of activity into a 5-minute morning briefing. "
            "Be concise, warm, and direct. "
            "Use plain prose — no bullet points. "
            "Maximum 300 words. "
            "If there are tasks pending approval, mention them prominently. "
            "If there are failed tasks, flag them as needing attention. "
            "End with a short paragraph listing any items that need the owner's approval, "
            "or say 'No approvals needed today.' if there are none."
        )

        try:
            summary = self._call_agent(prompt)
        except Exception as exc:
            logger.warning("generate(): agent call raised unexpectedly: %s", exc)
            summary = (
                "Good morning. Timmy is offline right now, so this briefing "
                "could not be generated from live data. Check that Ollama is "
                "running and try again."
            )

        # Attach any outstanding pending approval items
        approval_items = self._load_pending_items()

        briefing = Briefing(
            generated_at=now,
            summary=summary,
            approval_items=approval_items,
            period_start=period_start,
            period_end=now,
        )

        _save_briefing(briefing, self._db_path)
        logger.info("Briefing generated at %s", now.isoformat())
        return briefing

    def get_or_generate(self) -> Briefing:
        """Return a fresh cached briefing or generate a new one."""
        cached = _load_latest(self._db_path)
        if cached is not None and is_fresh(cached):
            # Reattach live pending items (they change between page loads)
            cached.approval_items = self._load_pending_items()
            return cached
        return self.generate()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_agent(self, prompt: str) -> str:
        """Call Timmy's Agno agent and return the response text."""
        try:
            from timmy.agent import create_timmy
            agent = create_timmy()
            run = agent.run(prompt, stream=False)
            return run.content if hasattr(run, "content") else str(run)
        except Exception as exc:
            logger.warning("Agent call failed during briefing generation: %s", exc)
            return (
                "Good morning. Timmy is offline right now, so this briefing "
                "could not be generated from live data. Check that Ollama is "
                "running and try again."
            )

    def _load_pending_items(self) -> list[ApprovalItem]:
        """Return pending ApprovalItems from the approvals DB."""
        try:
            from timmy import approvals as _approvals
            raw_items = _approvals.list_pending()
            return [
                ApprovalItem(
                    id=item.id,
                    title=item.title,
                    description=item.description,
                    proposed_action=item.proposed_action,
                    impact=item.impact,
                    created_at=item.created_at,
                    status=item.status,
                )
                for item in raw_items
            ]
        except Exception as exc:
            logger.debug("Could not load approval items: %s", exc)
            return []


# Module-level singleton
engine = BriefingEngine()
