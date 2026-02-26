"""Reference parser — extract and normalise biblical references from text.

Handles explicit references (``John 3:16``), range references
(``Romans 5:1-11``), multi-chapter ranges (``Genesis 1:1-2:3``),
and fuzzy book name matching (``1 Cor 13``, ``Phil 4 13``).
"""

from __future__ import annotations

import re
from typing import Optional

from scripture.constants import book_by_name, BookInfo, BOOK_BY_ID
from scripture.models import VerseRef, VerseRange


# ── Regex patterns ───────────────────────────────────────────────────────────

# Matches patterns like "John 3:16", "1 Cor 13:4-7", "Gen 1:1-2:3"
_REF_PATTERN = re.compile(
    r"""
    (?P<book>
        (?:[123]\s*)?            # optional ordinal (1, 2, 3)
        [A-Za-z]+                # book name
        (?:\s+of\s+[A-Za-z]+)?  # "Song of Solomon"
    )
    \s*
    (?P<chapter>\d{1,3})         # chapter number
    (?:
        \s*[:\.]\s*              # separator (colon or dot)
        (?P<verse>\d{1,3})       # verse number
        (?:
            \s*[-–—]\s*          # range separator
            (?:
                (?P<end_chapter>\d{1,3})  # optional end chapter
                \s*[:\.]\s*
            )?
            (?P<end_verse>\d{1,3})  # end verse
        )?
    )?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _normalise_book_name(raw: str) -> str:
    """Collapse whitespace and lowercase for lookup."""
    return re.sub(r"\s+", " ", raw.strip()).lower()


def resolve_book(name: str) -> Optional[BookInfo]:
    """Resolve a book name/abbreviation to a BookInfo."""
    return book_by_name(_normalise_book_name(name))


def parse_reference(text: str) -> Optional[VerseRange]:
    """Parse a single scripture reference string into a VerseRange.

    Examples::

        parse_reference("John 3:16")
        parse_reference("Genesis 1:1-3")
        parse_reference("Rom 5:1-11")
        parse_reference("1 Cor 13")  # whole chapter
    """
    m = _REF_PATTERN.search(text)
    if not m:
        return None

    book_info = resolve_book(m.group("book"))
    if not book_info:
        return None

    chapter = int(m.group("chapter"))
    verse_str = m.group("verse")
    end_verse_str = m.group("end_verse")
    end_chapter_str = m.group("end_chapter")

    if verse_str is None:
        # Whole chapter reference: "Genesis 1"
        start = VerseRef(book=book_info.id, chapter=chapter, verse=1)
        # Use a large verse number; the caller truncates to actual max
        end = VerseRef(book=book_info.id, chapter=chapter, verse=999)
        return VerseRange(start=start, end=end)

    start_verse = int(verse_str)
    start = VerseRef(book=book_info.id, chapter=chapter, verse=start_verse)

    if end_verse_str is not None:
        end_ch = int(end_chapter_str) if end_chapter_str else chapter
        end_v = int(end_verse_str)
        end = VerseRef(book=book_info.id, chapter=end_ch, verse=end_v)
    else:
        end = VerseRef(book=book_info.id, chapter=chapter, verse=start_verse)

    return VerseRange(start=start, end=end)


def extract_references(text: str) -> list[VerseRange]:
    """Extract all scripture references from a block of text.

    Returns a list of VerseRange objects for every reference found.
    """
    results: list[VerseRange] = []
    for m in _REF_PATTERN.finditer(text):
        book_info = resolve_book(m.group("book"))
        if not book_info:
            continue

        chapter = int(m.group("chapter"))
        verse_str = m.group("verse")
        end_verse_str = m.group("end_verse")
        end_chapter_str = m.group("end_chapter")

        if verse_str is None:
            start = VerseRef(book=book_info.id, chapter=chapter, verse=1)
            end = VerseRef(book=book_info.id, chapter=chapter, verse=999)
        else:
            sv = int(verse_str)
            start = VerseRef(book=book_info.id, chapter=chapter, verse=sv)
            if end_verse_str is not None:
                end_ch = int(end_chapter_str) if end_chapter_str else chapter
                end = VerseRef(book=book_info.id, chapter=end_ch, verse=int(end_verse_str))
            else:
                end = VerseRef(book=book_info.id, chapter=chapter, verse=sv)

        results.append(VerseRange(start=start, end=end))
    return results


def format_reference(ref: VerseRef) -> str:
    """Format a VerseRef as a human-readable string.

    Example: ``VerseRef(book=43, chapter=3, verse=16)`` → ``"John 3:16"``
    """
    book = BOOK_BY_ID.get(ref.book)
    if not book:
        return f"Unknown {ref.chapter}:{ref.verse}"
    if ref.verse == 0:
        return f"{book.name} {ref.chapter}"
    return f"{book.name} {ref.chapter}:{ref.verse}"


def format_range(vr: VerseRange) -> str:
    """Format a VerseRange as a human-readable string.

    Examples::

        "John 3:16"             (single verse)
        "Romans 5:1-11"         (same chapter range)
        "Genesis 1:1-2:3"       (multi-chapter range)
    """
    start_book = BOOK_BY_ID.get(vr.start.book)
    if not start_book:
        return "Unknown reference"

    if vr.start.verse_id == vr.end.verse_id:
        return format_reference(vr.start)

    if vr.start.chapter == vr.end.chapter:
        return f"{start_book.name} {vr.start.chapter}:{vr.start.verse}-{vr.end.verse}"

    return (
        f"{start_book.name} {vr.start.chapter}:{vr.start.verse}"
        f"-{vr.end.chapter}:{vr.end.verse}"
    )
