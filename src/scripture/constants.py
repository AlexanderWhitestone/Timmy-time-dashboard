"""Biblical constants — canonical book ordering, abbreviations, metadata.

The canon follows the standard 66-book Protestant ordering used by the ESV.
Each book is assigned a unique integer ID (1-66) for O(1) verse lookup via
the integer encoding scheme: book (1-2 digits) + chapter (3 digits) +
verse (3 digits).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class BookInfo:
    """Immutable metadata for a canonical book."""

    id: int
    name: str
    abbreviation: str
    testament: Literal["OT", "NT"]
    chapters: int
    genre: str


# ── Canonical book list (Protestant 66-book canon, ESV ordering) ────────────

BOOKS: tuple[BookInfo, ...] = (
    # ── Old Testament ────────────────────────────────────────────────────
    BookInfo(1, "Genesis", "Gen", "OT", 50, "law"),
    BookInfo(2, "Exodus", "Exod", "OT", 40, "law"),
    BookInfo(3, "Leviticus", "Lev", "OT", 27, "law"),
    BookInfo(4, "Numbers", "Num", "OT", 36, "law"),
    BookInfo(5, "Deuteronomy", "Deut", "OT", 34, "law"),
    BookInfo(6, "Joshua", "Josh", "OT", 24, "narrative"),
    BookInfo(7, "Judges", "Judg", "OT", 21, "narrative"),
    BookInfo(8, "Ruth", "Ruth", "OT", 4, "narrative"),
    BookInfo(9, "1 Samuel", "1Sam", "OT", 31, "narrative"),
    BookInfo(10, "2 Samuel", "2Sam", "OT", 24, "narrative"),
    BookInfo(11, "1 Kings", "1Kgs", "OT", 22, "narrative"),
    BookInfo(12, "2 Kings", "2Kgs", "OT", 25, "narrative"),
    BookInfo(13, "1 Chronicles", "1Chr", "OT", 29, "narrative"),
    BookInfo(14, "2 Chronicles", "2Chr", "OT", 36, "narrative"),
    BookInfo(15, "Ezra", "Ezra", "OT", 10, "narrative"),
    BookInfo(16, "Nehemiah", "Neh", "OT", 13, "narrative"),
    BookInfo(17, "Esther", "Esth", "OT", 10, "narrative"),
    BookInfo(18, "Job", "Job", "OT", 42, "wisdom"),
    BookInfo(19, "Psalms", "Ps", "OT", 150, "wisdom"),
    BookInfo(20, "Proverbs", "Prov", "OT", 31, "wisdom"),
    BookInfo(21, "Ecclesiastes", "Eccl", "OT", 12, "wisdom"),
    BookInfo(22, "Song of Solomon", "Song", "OT", 8, "wisdom"),
    BookInfo(23, "Isaiah", "Isa", "OT", 66, "prophecy"),
    BookInfo(24, "Jeremiah", "Jer", "OT", 52, "prophecy"),
    BookInfo(25, "Lamentations", "Lam", "OT", 5, "prophecy"),
    BookInfo(26, "Ezekiel", "Ezek", "OT", 48, "prophecy"),
    BookInfo(27, "Daniel", "Dan", "OT", 12, "prophecy"),
    BookInfo(28, "Hosea", "Hos", "OT", 14, "prophecy"),
    BookInfo(29, "Joel", "Joel", "OT", 3, "prophecy"),
    BookInfo(30, "Amos", "Amos", "OT", 9, "prophecy"),
    BookInfo(31, "Obadiah", "Obad", "OT", 1, "prophecy"),
    BookInfo(32, "Jonah", "Jonah", "OT", 4, "prophecy"),
    BookInfo(33, "Micah", "Mic", "OT", 7, "prophecy"),
    BookInfo(34, "Nahum", "Nah", "OT", 3, "prophecy"),
    BookInfo(35, "Habakkuk", "Hab", "OT", 3, "prophecy"),
    BookInfo(36, "Zephaniah", "Zeph", "OT", 3, "prophecy"),
    BookInfo(37, "Haggai", "Hag", "OT", 2, "prophecy"),
    BookInfo(38, "Zechariah", "Zech", "OT", 14, "prophecy"),
    BookInfo(39, "Malachi", "Mal", "OT", 4, "prophecy"),
    # ── New Testament ────────────────────────────────────────────────────
    BookInfo(40, "Matthew", "Matt", "NT", 28, "gospel"),
    BookInfo(41, "Mark", "Mark", "NT", 16, "gospel"),
    BookInfo(42, "Luke", "Luke", "NT", 24, "gospel"),
    BookInfo(43, "John", "John", "NT", 21, "gospel"),
    BookInfo(44, "Acts", "Acts", "NT", 28, "narrative"),
    BookInfo(45, "Romans", "Rom", "NT", 16, "epistle"),
    BookInfo(46, "1 Corinthians", "1Cor", "NT", 16, "epistle"),
    BookInfo(47, "2 Corinthians", "2Cor", "NT", 13, "epistle"),
    BookInfo(48, "Galatians", "Gal", "NT", 6, "epistle"),
    BookInfo(49, "Ephesians", "Eph", "NT", 6, "epistle"),
    BookInfo(50, "Philippians", "Phil", "NT", 4, "epistle"),
    BookInfo(51, "Colossians", "Col", "NT", 4, "epistle"),
    BookInfo(52, "1 Thessalonians", "1Thess", "NT", 5, "epistle"),
    BookInfo(53, "2 Thessalonians", "2Thess", "NT", 3, "epistle"),
    BookInfo(54, "1 Timothy", "1Tim", "NT", 6, "epistle"),
    BookInfo(55, "2 Timothy", "2Tim", "NT", 4, "epistle"),
    BookInfo(56, "Titus", "Titus", "NT", 3, "epistle"),
    BookInfo(57, "Philemon", "Phlm", "NT", 1, "epistle"),
    BookInfo(58, "Hebrews", "Heb", "NT", 13, "epistle"),
    BookInfo(59, "James", "Jas", "NT", 5, "epistle"),
    BookInfo(60, "1 Peter", "1Pet", "NT", 5, "epistle"),
    BookInfo(61, "2 Peter", "2Pet", "NT", 3, "epistle"),
    BookInfo(62, "1 John", "1John", "NT", 5, "epistle"),
    BookInfo(63, "2 John", "2John", "NT", 1, "epistle"),
    BookInfo(64, "3 John", "3John", "NT", 1, "epistle"),
    BookInfo(65, "Jude", "Jude", "NT", 1, "epistle"),
    BookInfo(66, "Revelation", "Rev", "NT", 22, "apocalyptic"),
)

# ── Lookup indices (built once at import time) ──────────────────────────────

BOOK_BY_ID: dict[int, BookInfo] = {b.id: b for b in BOOKS}

# Map both full names and abbreviations (case-insensitive) to BookInfo
_BOOK_NAME_MAP: dict[str, BookInfo] = {}
for _b in BOOKS:
    _BOOK_NAME_MAP[_b.name.lower()] = _b
    _BOOK_NAME_MAP[_b.abbreviation.lower()] = _b

# Common aliases people use that differ from the canonical abbreviation
_ALIASES: dict[str, int] = {
    "ge": 1, "gen": 1, "genesis": 1,
    "ex": 2, "exo": 2, "exodus": 2,
    "le": 3, "lev": 3, "leviticus": 3,
    "nu": 4, "num": 4, "numbers": 4,
    "dt": 5, "deut": 5, "deuteronomy": 5,
    "jos": 6, "josh": 6, "joshua": 6,
    "jdg": 7, "judg": 7, "judges": 7,
    "ru": 8, "ruth": 8,
    "1sa": 9, "1sam": 9, "1 samuel": 9, "i samuel": 9, "1st samuel": 9,
    "2sa": 10, "2sam": 10, "2 samuel": 10, "ii samuel": 10, "2nd samuel": 10,
    "1ki": 11, "1kgs": 11, "1 kings": 11, "i kings": 11, "1st kings": 11,
    "2ki": 12, "2kgs": 12, "2 kings": 12, "ii kings": 12, "2nd kings": 12,
    "1ch": 13, "1chr": 13, "1 chronicles": 13, "i chronicles": 13,
    "2ch": 14, "2chr": 14, "2 chronicles": 14, "ii chronicles": 14,
    "ezr": 15, "ezra": 15,
    "ne": 16, "neh": 16, "nehemiah": 16,
    "est": 17, "esth": 17, "esther": 17,
    "job": 18,
    "ps": 19, "psa": 19, "psalm": 19, "psalms": 19,
    "pr": 20, "prov": 20, "proverbs": 20,
    "ec": 21, "eccl": 21, "ecclesiastes": 21, "ecc": 21,
    "so": 22, "song": 22, "song of solomon": 22, "song of songs": 22, "sos": 22,
    "isa": 23, "isaiah": 23,
    "jer": 24, "jeremiah": 24,
    "la": 25, "lam": 25, "lamentations": 25,
    "eze": 26, "ezek": 26, "ezekiel": 26,
    "da": 27, "dan": 27, "daniel": 27,
    "ho": 28, "hos": 28, "hosea": 28,
    "joe": 29, "joel": 29,
    "am": 30, "amos": 30,
    "ob": 31, "obad": 31, "obadiah": 31,
    "jon": 32, "jonah": 32,
    "mi": 33, "mic": 33, "micah": 33,
    "na": 34, "nah": 34, "nahum": 34,
    "hab": 35, "habakkuk": 35,
    "zep": 36, "zeph": 36, "zephaniah": 36,
    "hag": 37, "haggai": 37,
    "zec": 38, "zech": 38, "zechariah": 38,
    "mal": 39, "malachi": 39,
    "mt": 40, "matt": 40, "matthew": 40, "mat": 40,
    "mk": 41, "mark": 41, "mar": 41,
    "lk": 42, "luke": 42, "lu": 42,
    "jn": 43, "john": 43, "joh": 43,
    "ac": 44, "acts": 44, "act": 44,
    "ro": 45, "rom": 45, "romans": 45,
    "1co": 46, "1cor": 46, "1 cor": 46, "1 corinthians": 46, "i corinthians": 46,
    "2co": 47, "2cor": 47, "2 cor": 47, "2 corinthians": 47, "ii corinthians": 47,
    "ga": 48, "gal": 48, "galatians": 48,
    "eph": 49, "ephesians": 49,
    "php": 50, "phil": 50, "philippians": 50,
    "col": 51, "colossians": 51,
    "1th": 52, "1thess": 52, "1 thessalonians": 52, "i thessalonians": 52,
    "2th": 53, "2thess": 53, "2 thessalonians": 53, "ii thessalonians": 53,
    "1ti": 54, "1tim": 54, "1 timothy": 54, "i timothy": 54,
    "2ti": 55, "2tim": 55, "2 timothy": 55, "ii timothy": 55,
    "tit": 56, "titus": 56,
    "phm": 57, "phlm": 57, "philemon": 57,
    "heb": 58, "hebrews": 58,
    "jas": 59, "james": 59, "jam": 59,
    "1pe": 60, "1pet": 60, "1 peter": 60, "i peter": 60, "1st peter": 60,
    "2pe": 61, "2pet": 61, "2 peter": 61, "ii peter": 61, "2nd peter": 61,
    "1jn": 62, "1john": 62, "1 john": 62, "i john": 62, "1st john": 62,
    "2jn": 63, "2john": 63, "2 john": 63, "ii john": 63, "2nd john": 63,
    "3jn": 64, "3john": 64, "3 john": 64, "iii john": 64, "3rd john": 64,
    "jude": 65, "jud": 65,
    "re": 66, "rev": 66, "revelation": 66, "revelations": 66,
}

for _alias, _bid in _ALIASES.items():
    _BOOK_NAME_MAP.setdefault(_alias, BOOK_BY_ID[_bid])

TOTAL_BOOKS = 66
OT_BOOKS = 39
NT_BOOKS = 27

GENRES = frozenset(b.genre for b in BOOKS)


def book_by_name(name: str) -> BookInfo | None:
    """Resolve a book name or abbreviation to a BookInfo (case-insensitive)."""
    return _BOOK_NAME_MAP.get(name.strip().lower())


def book_by_id(book_id: int) -> BookInfo | None:
    """Return the BookInfo for a canonical book ID (1-66)."""
    return BOOK_BY_ID.get(book_id)
