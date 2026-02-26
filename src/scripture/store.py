"""Scripture store — SQLite-backed verse storage and retrieval.

Provides the persistent knowledge base for the complete ESV text.
Follows the project's SQLite singleton pattern (cf. swarm/registry.py).

Tables
------
- ``verses``          Primary verse storage with text + metadata
- ``cross_references`` TSK-derived edges between verses
- ``topics``          Nave's-style topical index entries
- ``verse_topics``    Many-to-many verse ↔ topic links
- ``strongs``         Strong's concordance entries
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from scripture.constants import BOOK_BY_ID, book_by_name
from scripture.models import (
    CrossReference,
    StrongsEntry,
    Topic,
    Verse,
    VerseRef,
    decode_verse_id,
    encode_verse_id,
)

logger = logging.getLogger(__name__)

DB_DIR = Path("data")
DB_PATH = DB_DIR / "scripture.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS verses (
    verse_id   INTEGER PRIMARY KEY,
    book       INTEGER NOT NULL,
    chapter    INTEGER NOT NULL,
    verse_num  INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    translation TEXT   NOT NULL DEFAULT 'ESV',
    testament  TEXT    NOT NULL DEFAULT 'OT',
    genre      TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_verses_book_ch
    ON verses(book, chapter);

CREATE TABLE IF NOT EXISTS cross_references (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_verse_id INTEGER NOT NULL,
    target_verse_id INTEGER NOT NULL,
    reference_type  TEXT    NOT NULL DEFAULT 'thematic',
    confidence      REAL    NOT NULL DEFAULT 1.0,
    UNIQUE(source_verse_id, target_verse_id, reference_type)
);

CREATE INDEX IF NOT EXISTS idx_xref_source
    ON cross_references(source_verse_id);
CREATE INDEX IF NOT EXISTS idx_xref_target
    ON cross_references(target_verse_id);

CREATE TABLE IF NOT EXISTS topics (
    topic_id    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   TEXT,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS verse_topics (
    verse_id  INTEGER NOT NULL,
    topic_id  TEXT    NOT NULL,
    relevance REAL    NOT NULL DEFAULT 1.0,
    PRIMARY KEY (verse_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_vt_topic
    ON verse_topics(topic_id);

CREATE TABLE IF NOT EXISTS strongs (
    strongs_number TEXT PRIMARY KEY,
    language       TEXT NOT NULL,
    lemma          TEXT NOT NULL DEFAULT '',
    transliteration TEXT NOT NULL DEFAULT '',
    gloss          TEXT NOT NULL DEFAULT '',
    morphology     TEXT NOT NULL DEFAULT ''
);
"""


class ScriptureStore:
    """SQLite-backed scripture knowledge base.

    Usage::

        from scripture.store import scripture_store
        verse = scripture_store.get_verse(43, 3, 16)
    """

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ── Connection management ────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Verse CRUD ───────────────────────────────────────────────────────

    def insert_verse(self, verse: Verse) -> None:
        """Insert or replace a single verse."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO verses
               (verse_id, book, chapter, verse_num, text, translation, testament, genre)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                verse.verse_id,
                verse.book,
                verse.chapter,
                verse.verse_num,
                verse.text,
                verse.translation,
                verse.testament,
                verse.genre,
            ),
        )
        conn.commit()

    def insert_verses(self, verses: list[Verse]) -> None:
        """Bulk-insert verses (efficient for full-text ingestion)."""
        conn = self._get_conn()
        conn.executemany(
            """INSERT OR REPLACE INTO verses
               (verse_id, book, chapter, verse_num, text, translation, testament, genre)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (v.verse_id, v.book, v.chapter, v.verse_num,
                 v.text, v.translation, v.testament, v.genre)
                for v in verses
            ],
        )
        conn.commit()

    def get_verse(self, book: int, chapter: int, verse: int) -> Optional[Verse]:
        """Retrieve a single verse by book/chapter/verse."""
        vid = encode_verse_id(book, chapter, verse)
        row = self._get_conn().execute(
            "SELECT * FROM verses WHERE verse_id = ?", (vid,)
        ).fetchone()
        return self._row_to_verse(row) if row else None

    def get_verse_by_id(self, verse_id: int) -> Optional[Verse]:
        """Retrieve a verse by its integer ID."""
        row = self._get_conn().execute(
            "SELECT * FROM verses WHERE verse_id = ?", (verse_id,)
        ).fetchone()
        return self._row_to_verse(row) if row else None

    def get_chapter(self, book: int, chapter: int) -> list[Verse]:
        """Retrieve all verses in a chapter, ordered by verse number."""
        rows = self._get_conn().execute(
            "SELECT * FROM verses WHERE book = ? AND chapter = ? ORDER BY verse_num",
            (book, chapter),
        ).fetchall()
        return [self._row_to_verse(r) for r in rows]

    def get_range(self, start_id: int, end_id: int) -> list[Verse]:
        """Retrieve all verses in a range of verse IDs (inclusive)."""
        rows = self._get_conn().execute(
            "SELECT * FROM verses WHERE verse_id BETWEEN ? AND ? ORDER BY verse_id",
            (start_id, end_id),
        ).fetchall()
        return [self._row_to_verse(r) for r in rows]

    def search_text(self, query: str, limit: int = 20) -> list[Verse]:
        """Full-text search across verse content (LIKE-based)."""
        rows = self._get_conn().execute(
            "SELECT * FROM verses WHERE text LIKE ? ORDER BY verse_id LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_verse(r) for r in rows]

    def count_verses(self) -> int:
        """Return the total number of verses in the store."""
        row = self._get_conn().execute("SELECT COUNT(*) FROM verses").fetchone()
        return row[0] if row else 0

    def get_books(self) -> list[dict]:
        """Return a summary of all books with verse counts."""
        rows = self._get_conn().execute(
            """SELECT book, COUNT(*) as verse_count, MIN(chapter) as min_ch,
                      MAX(chapter) as max_ch
               FROM verses GROUP BY book ORDER BY book"""
        ).fetchall()
        result = []
        for r in rows:
            info = BOOK_BY_ID.get(r["book"])
            result.append({
                "book_id": r["book"],
                "name": info.name if info else f"Book {r['book']}",
                "abbreviation": info.abbreviation if info else "",
                "testament": info.testament if info else "",
                "verse_count": r["verse_count"],
                "chapters": r["max_ch"],
            })
        return result

    # ── Cross-references ─────────────────────────────────────────────────

    def insert_cross_reference(self, xref: CrossReference) -> None:
        """Insert a cross-reference link."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO cross_references
               (source_verse_id, target_verse_id, reference_type, confidence)
               VALUES (?, ?, ?, ?)""",
            (xref.source_verse_id, xref.target_verse_id,
             xref.reference_type, xref.confidence),
        )
        conn.commit()

    def get_cross_references(self, verse_id: int) -> list[CrossReference]:
        """Find all cross-references from or to a verse."""
        rows = self._get_conn().execute(
            """SELECT * FROM cross_references
               WHERE source_verse_id = ? OR target_verse_id = ?
               ORDER BY confidence DESC""",
            (verse_id, verse_id),
        ).fetchall()
        return [
            CrossReference(
                source_verse_id=r["source_verse_id"],
                target_verse_id=r["target_verse_id"],
                reference_type=r["reference_type"],
                confidence=r["confidence"],
            )
            for r in rows
        ]

    # ── Topics ───────────────────────────────────────────────────────────

    def insert_topic(self, topic: Topic) -> None:
        """Insert a topical index entry."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO topics
               (topic_id, name, parent_id, description) VALUES (?, ?, ?, ?)""",
            (topic.topic_id, topic.name, topic.parent_id, topic.description),
        )
        for vid in topic.verse_ids:
            conn.execute(
                "INSERT OR IGNORE INTO verse_topics (verse_id, topic_id) VALUES (?, ?)",
                (vid, topic.topic_id),
            )
        conn.commit()

    def get_topic(self, topic_id: str) -> Optional[Topic]:
        """Retrieve a topic by ID."""
        row = self._get_conn().execute(
            "SELECT * FROM topics WHERE topic_id = ?", (topic_id,)
        ).fetchone()
        if not row:
            return None
        verse_rows = self._get_conn().execute(
            "SELECT verse_id FROM verse_topics WHERE topic_id = ?", (topic_id,)
        ).fetchall()
        return Topic(
            topic_id=row["topic_id"],
            name=row["name"],
            parent_id=row["parent_id"],
            description=row["description"],
            verse_ids=[r["verse_id"] for r in verse_rows],
        )

    def search_topics(self, query: str, limit: int = 10) -> list[Topic]:
        """Search topics by name."""
        rows = self._get_conn().execute(
            "SELECT * FROM topics WHERE name LIKE ? ORDER BY name LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [
            Topic(topic_id=r["topic_id"], name=r["name"],
                  parent_id=r["parent_id"], description=r["description"])
            for r in rows
        ]

    def get_verses_for_topic(self, topic_id: str) -> list[Verse]:
        """Retrieve all verses associated with a topic."""
        rows = self._get_conn().execute(
            """SELECT v.* FROM verses v
               INNER JOIN verse_topics vt ON v.verse_id = vt.verse_id
               WHERE vt.topic_id = ?
               ORDER BY v.verse_id""",
            (topic_id,),
        ).fetchall()
        return [self._row_to_verse(r) for r in rows]

    # ── Strong's concordance ─────────────────────────────────────────────

    def insert_strongs(self, entry: StrongsEntry) -> None:
        """Insert a Strong's concordance entry."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO strongs
               (strongs_number, language, lemma, transliteration, gloss, morphology)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entry.strongs_number, entry.language, entry.lemma,
             entry.transliteration, entry.gloss, entry.morphology),
        )
        conn.commit()

    def get_strongs(self, number: str) -> Optional[StrongsEntry]:
        """Look up a Strong's number."""
        row = self._get_conn().execute(
            "SELECT * FROM strongs WHERE strongs_number = ?", (number,)
        ).fetchone()
        if not row:
            return None
        return StrongsEntry(
            strongs_number=row["strongs_number"],
            language=row["language"],
            lemma=row["lemma"],
            transliteration=row["transliteration"],
            gloss=row["gloss"],
            morphology=row["morphology"],
        )

    # ── Stats ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return summary statistics of the scripture store."""
        conn = self._get_conn()
        verses = conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
        xrefs = conn.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
        topics = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        strongs = conn.execute("SELECT COUNT(*) FROM strongs").fetchone()[0]
        return {
            "verses": verses,
            "cross_references": xrefs,
            "topics": topics,
            "strongs_entries": strongs,
        }

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_verse(row: sqlite3.Row) -> Verse:
        return Verse(
            verse_id=row["verse_id"],
            book=row["book"],
            chapter=row["chapter"],
            verse_num=row["verse_num"],
            text=row["text"],
            translation=row["translation"],
            testament=row["testament"],
            genre=row["genre"],
        )


# Module-level singleton
scripture_store = ScriptureStore()
