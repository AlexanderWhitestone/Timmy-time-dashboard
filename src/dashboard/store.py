"""SQLite-backed chat history for the dashboard.

The MessageLog provides a persistent record of all chat interactions,
ensuring that the conversation history survives server restarts.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

DB_PATH = Path("timmy.db")


@dataclass
class Message:
    role: str       # "user" | "agent" | "error"
    content: str
    timestamp: str


def init_db(db_path: Path) -> None:
    """Initialize the messages table if it doesn't exist."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


class MessageLog:
    """Persistent chat history using SQLite."""

    def __init__(self) -> None:
        pass

    def _get_conn(self) -> sqlite3.Connection:
        init_db(DB_PATH)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def append(self, role: str, content: str, timestamp: str) -> None:
        """Add a new message to the persistent log."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO messages (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, timestamp),
        )
        conn.commit()
        conn.close()

    def all(self) -> List[Message]:
        """Retrieve all messages from the log."""
        conn = self._get_conn()
        rows = conn.execute("SELECT role, content, timestamp FROM messages ORDER BY id ASC").fetchall()
        conn.close()
        return [Message(role=r["role"], content=r["content"], timestamp=r["timestamp"]) for r in rows]

    def clear(self) -> None:
        """Delete all messages from the log."""
        conn = self._get_conn()
        conn.execute("DELETE FROM messages")
        conn.commit()
        conn.close()

    def __len__(self) -> int:
        conn = self._get_conn()
        count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        conn.close()
        return count


# Module-level singleton shared across the app
message_log = MessageLog()
