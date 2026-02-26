"""Data models for the scripture module.

Provides Pydantic models for verses, references, cross-references,
topics, and original language annotations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Integer encoding scheme ──────────────────────────────────────────────────
# book (1-66, 1-2 digits) + chapter (3 digits, zero-padded) +
# verse (3 digits, zero-padded) = 7-8 digit unique integer per verse.
# Example: John 3:16 → 43_003_016 = 43003016


def encode_verse_id(book: int, chapter: int, verse: int) -> int:
    """Encode a book/chapter/verse triplet into a unique integer ID."""
    return book * 1_000_000 + chapter * 1_000 + verse


def decode_verse_id(verse_id: int) -> tuple[int, int, int]:
    """Decode an integer verse ID back to (book, chapter, verse)."""
    book = verse_id // 1_000_000
    remainder = verse_id % 1_000_000
    chapter = remainder // 1_000
    verse = remainder % 1_000
    return book, chapter, verse


# ── Core models ──────────────────────────────────────────────────────────────


class VerseRef(BaseModel):
    """A single verse reference (book + chapter + verse)."""

    book: int = Field(ge=1, le=66, description="Canonical book ID (1-66)")
    chapter: int = Field(ge=1, description="Chapter number")
    verse: int = Field(ge=0, description="Verse number (0 for chapter-level)")

    @property
    def verse_id(self) -> int:
        return encode_verse_id(self.book, self.chapter, self.verse)


class VerseRange(BaseModel):
    """A contiguous range of verses."""

    start: VerseRef
    end: VerseRef

    def verse_ids(self) -> list[int]:
        """Expand the range to individual verse IDs."""
        ids = []
        for vid in range(self.start.verse_id, self.end.verse_id + 1):
            b, c, v = decode_verse_id(vid)
            if 1 <= b <= 66 and c >= 1 and v >= 1:
                ids.append(vid)
        return ids


class Verse(BaseModel):
    """A single verse with text content and metadata."""

    verse_id: int = Field(description="Encoded integer ID")
    book: int
    chapter: int
    verse_num: int
    text: str
    translation: str = "ESV"
    testament: Literal["OT", "NT"] = "OT"
    genre: str = ""


class CrossReference(BaseModel):
    """A cross-reference link between two verses."""

    source_verse_id: int
    target_verse_id: int
    reference_type: Literal[
        "quotation", "allusion", "thematic", "typology", "parallel"
    ] = "thematic"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class Topic(BaseModel):
    """A topical category from a topical index (e.g. Nave's)."""

    topic_id: str
    name: str
    parent_id: Optional[str] = None
    description: str = ""
    verse_ids: list[int] = Field(default_factory=list)


class StrongsEntry(BaseModel):
    """A Strong's concordance entry for original language terms."""

    strongs_number: str = Field(description="e.g. H7225, G26")
    language: Literal["hebrew", "greek"]
    lemma: str = ""
    transliteration: str = ""
    gloss: str = ""
    morphology: str = ""


class OriginalLanguageToken(BaseModel):
    """A token in original language text with annotations."""

    text: str
    transliteration: str = ""
    strongs_number: str = ""
    morphology: str = ""
    gloss: str = ""
    word_position: int = 0


class InterlinearVerse(BaseModel):
    """A verse with interlinear original language alignment."""

    verse_id: int
    reference: str
    original_tokens: list[OriginalLanguageToken] = Field(default_factory=list)
    esv_text: str = ""
    language: Literal["hebrew", "greek"] = "hebrew"


class MeditationState(BaseModel):
    """Tracks the current meditation progress."""

    current_book: int = 1
    current_chapter: int = 1
    current_verse: int = 1
    mode: Literal["sequential", "thematic", "lectionary"] = "sequential"
    theme: Optional[str] = None
    last_meditation: Optional[str] = None
    verses_meditated: int = 0

    def advance(self, book: int, chapter: int, verse: int) -> None:
        self.current_book = book
        self.current_chapter = chapter
        self.current_verse = verse
        self.last_meditation = datetime.now(timezone.utc).isoformat()
        self.verses_meditated += 1


class ScriptureQuery(BaseModel):
    """A parsed user query for scripture content."""

    intent: Literal[
        "lookup", "explanation", "application", "comparison", "devotional", "search"
    ] = "lookup"
    references: list[VerseRef] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    topic: Optional[str] = None
    raw_text: str = ""
