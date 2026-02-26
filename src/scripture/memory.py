"""Scripture memory system — working, long-term, and associative memory.

Provides the tripartite memory architecture for continuous scriptural
engagement:

- **Working memory**: active passage under meditation (session-scoped)
- **Long-term memory**: persistent store of the full biblical corpus
  (delegated to ScriptureStore)
- **Associative memory**: thematic and conceptual linkages between verses

The meditation scheduler uses this module to maintain "always on its mind"
engagement with scripture.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scripture.models import MeditationState, Verse, decode_verse_id

logger = logging.getLogger(__name__)

# Working memory capacity (analogous to 7±2 human working memory)
WORKING_MEMORY_CAPACITY = 7

_MEM_DB_DIR = Path("data")
_MEM_DB_PATH = _MEM_DB_DIR / "scripture.db"

_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS meditation_state (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    current_book   INTEGER NOT NULL DEFAULT 1,
    current_chapter INTEGER NOT NULL DEFAULT 1,
    current_verse  INTEGER NOT NULL DEFAULT 1,
    mode           TEXT    NOT NULL DEFAULT 'sequential',
    theme          TEXT,
    last_meditation TEXT,
    verses_meditated INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meditation_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    verse_id   INTEGER NOT NULL,
    meditated_at TEXT NOT NULL,
    notes      TEXT NOT NULL DEFAULT '',
    mode       TEXT NOT NULL DEFAULT 'sequential'
);

CREATE INDEX IF NOT EXISTS idx_meditation_log_verse
    ON meditation_log(verse_id);

CREATE TABLE IF NOT EXISTS verse_insights (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    verse_id   INTEGER NOT NULL,
    insight    TEXT    NOT NULL,
    category   TEXT    NOT NULL DEFAULT 'general',
    created_at TEXT    NOT NULL,
    UNIQUE(verse_id, insight)
);
"""


class WorkingMemory:
    """Session-scoped memory for actively meditated passages.

    Holds the most recent ``WORKING_MEMORY_CAPACITY`` verses in focus.
    Uses an LRU-style eviction: oldest items drop when capacity is exceeded.
    """

    def __init__(self, capacity: int = WORKING_MEMORY_CAPACITY) -> None:
        self._capacity = capacity
        self._items: OrderedDict[int, Verse] = OrderedDict()

    def focus(self, verse: Verse) -> None:
        """Bring a verse into working memory (or refresh if already present)."""
        if verse.verse_id in self._items:
            self._items.move_to_end(verse.verse_id)
        else:
            self._items[verse.verse_id] = verse
            if len(self._items) > self._capacity:
                self._items.popitem(last=False)

    def get_focused(self) -> list[Verse]:
        """Return all verses currently in working memory (most recent last)."""
        return list(self._items.values())

    def is_focused(self, verse_id: int) -> bool:
        return verse_id in self._items

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


class AssociativeMemory:
    """Thematic and conceptual linkages between verses.

    Associates verses with insights and connections discovered during
    meditation.  Persisted to SQLite for cross-session continuity.
    """

    def __init__(self, db_path: Path | str = _MEM_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_MEMORY_SCHEMA)
        # Ensure the singleton meditation state row exists
        conn.execute(
            "INSERT OR IGNORE INTO meditation_state (id) VALUES (1)"
        )
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Meditation state persistence ─────────────────────────────────────

    def get_meditation_state(self) -> MeditationState:
        """Load the current meditation progress."""
        row = self._get_conn().execute(
            "SELECT * FROM meditation_state WHERE id = 1"
        ).fetchone()
        if not row:
            return MeditationState()
        return MeditationState(
            current_book=row["current_book"],
            current_chapter=row["current_chapter"],
            current_verse=row["current_verse"],
            mode=row["mode"],
            theme=row["theme"],
            last_meditation=row["last_meditation"],
            verses_meditated=row["verses_meditated"],
        )

    def save_meditation_state(self, state: MeditationState) -> None:
        """Persist the meditation state."""
        conn = self._get_conn()
        conn.execute(
            """UPDATE meditation_state SET
                current_book = ?, current_chapter = ?, current_verse = ?,
                mode = ?, theme = ?, last_meditation = ?, verses_meditated = ?
               WHERE id = 1""",
            (
                state.current_book, state.current_chapter, state.current_verse,
                state.mode, state.theme, state.last_meditation,
                state.verses_meditated,
            ),
        )
        conn.commit()

    # ── Meditation log ───────────────────────────────────────────────────

    def log_meditation(
        self, verse_id: int, notes: str = "", mode: str = "sequential"
    ) -> None:
        """Record that a verse was meditated upon."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO meditation_log (verse_id, meditated_at, notes, mode) VALUES (?, ?, ?, ?)",
            (verse_id, datetime.now(timezone.utc).isoformat(), notes, mode),
        )
        conn.commit()

    def get_meditation_history(self, limit: int = 20) -> list[dict]:
        """Return the most recent meditation log entries."""
        rows = self._get_conn().execute(
            "SELECT * FROM meditation_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "verse_id": r["verse_id"],
                "meditated_at": r["meditated_at"],
                "notes": r["notes"],
                "mode": r["mode"],
            }
            for r in rows
        ]

    def meditation_count(self) -> int:
        """Total meditation sessions logged."""
        row = self._get_conn().execute(
            "SELECT COUNT(*) FROM meditation_log"
        ).fetchone()
        return row[0] if row else 0

    # ── Verse insights ───────────────────────────────────────────────────

    def add_insight(
        self, verse_id: int, insight: str, category: str = "general"
    ) -> None:
        """Record an insight discovered during meditation or study."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO verse_insights
               (verse_id, insight, category, created_at) VALUES (?, ?, ?, ?)""",
            (verse_id, insight, category, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    def get_insights(self, verse_id: int) -> list[dict]:
        """Retrieve all insights for a given verse."""
        rows = self._get_conn().execute(
            "SELECT * FROM verse_insights WHERE verse_id = ? ORDER BY created_at DESC",
            (verse_id,),
        ).fetchall()
        return [
            {
                "insight": r["insight"],
                "category": r["category"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get_recent_insights(self, limit: int = 10) -> list[dict]:
        """Return the most recently added insights across all verses."""
        rows = self._get_conn().execute(
            "SELECT * FROM verse_insights ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "verse_id": r["verse_id"],
                "insight": r["insight"],
                "category": r["category"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


class ScriptureMemory:
    """Unified scripture memory manager combining all three memory tiers.

    Usage::

        from scripture.memory import scripture_memory
        scripture_memory.working.focus(verse)
        state = scripture_memory.associative.get_meditation_state()
    """

    def __init__(self, db_path: Path | str = _MEM_DB_PATH) -> None:
        self.working = WorkingMemory()
        self.associative = AssociativeMemory(db_path=db_path)

    def close(self) -> None:
        self.working.clear()
        self.associative.close()

    def status(self) -> dict:
        """Return a summary of memory system state."""
        state = self.associative.get_meditation_state()
        return {
            "working_memory_items": len(self.working),
            "working_memory_capacity": WORKING_MEMORY_CAPACITY,
            "meditation_mode": state.mode,
            "verses_meditated": state.verses_meditated,
            "last_meditation": state.last_meditation,
            "meditation_count": self.associative.meditation_count(),
        }


# Module-level singleton
scripture_memory = ScriptureMemory()
