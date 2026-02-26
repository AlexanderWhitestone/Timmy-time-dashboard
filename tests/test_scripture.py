"""Tests for the scripture module — sovereign biblical text integration.

Covers: constants, models, parser, store, memory, meditation, and routes.
All tests use in-memory or temp-file SQLite — no external services needed.
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ════════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════════


class TestConstants:
    def test_total_books(self):
        from scripture.constants import BOOKS, TOTAL_BOOKS
        assert len(BOOKS) == TOTAL_BOOKS == 66

    def test_ot_nt_split(self):
        from scripture.constants import BOOKS, OT_BOOKS, NT_BOOKS
        ot = [b for b in BOOKS if b.testament == "OT"]
        nt = [b for b in BOOKS if b.testament == "NT"]
        assert len(ot) == OT_BOOKS == 39
        assert len(nt) == NT_BOOKS == 27

    def test_book_ids_sequential(self):
        from scripture.constants import BOOKS
        for i, book in enumerate(BOOKS, start=1):
            assert book.id == i, f"Book {book.name} has id {book.id}, expected {i}"

    def test_book_by_name_full(self):
        from scripture.constants import book_by_name
        info = book_by_name("Genesis")
        assert info is not None
        assert info.id == 1
        assert info.testament == "OT"

    def test_book_by_name_abbreviation(self):
        from scripture.constants import book_by_name
        info = book_by_name("Rev")
        assert info is not None
        assert info.id == 66
        assert info.name == "Revelation"

    def test_book_by_name_case_insensitive(self):
        from scripture.constants import book_by_name
        assert book_by_name("JOHN") is not None
        assert book_by_name("john") is not None
        assert book_by_name("John") is not None

    def test_book_by_name_alias(self):
        from scripture.constants import book_by_name
        assert book_by_name("1 Cor").id == 46
        assert book_by_name("Phil").id == 50
        assert book_by_name("Ps").id == 19

    def test_book_by_name_unknown(self):
        from scripture.constants import book_by_name
        assert book_by_name("Nonexistent") is None

    def test_book_by_id(self):
        from scripture.constants import book_by_id
        info = book_by_id(43)
        assert info is not None
        assert info.name == "John"

    def test_book_by_id_invalid(self):
        from scripture.constants import book_by_id
        assert book_by_id(0) is None
        assert book_by_id(67) is None

    def test_genres_present(self):
        from scripture.constants import GENRES
        assert "gospel" in GENRES
        assert "epistle" in GENRES
        assert "wisdom" in GENRES
        assert "prophecy" in GENRES

    def test_first_and_last_books(self):
        from scripture.constants import BOOKS
        assert BOOKS[0].name == "Genesis"
        assert BOOKS[-1].name == "Revelation"


# ════════════════════════════════════════════════════════════════════════════
# Models
# ════════════════════════════════════════════════════════════════════════════


class TestModels:
    def test_encode_verse_id(self):
        from scripture.models import encode_verse_id
        assert encode_verse_id(43, 3, 16) == 43003016
        assert encode_verse_id(1, 1, 1) == 1001001
        assert encode_verse_id(66, 22, 21) == 66022021

    def test_decode_verse_id(self):
        from scripture.models import decode_verse_id
        assert decode_verse_id(43003016) == (43, 3, 16)
        assert decode_verse_id(1001001) == (1, 1, 1)
        assert decode_verse_id(66022021) == (66, 22, 21)

    def test_encode_decode_roundtrip(self):
        from scripture.models import decode_verse_id, encode_verse_id
        for book in (1, 19, 43, 66):
            for chapter in (1, 10, 50):
                for verse in (1, 5, 31):
                    vid = encode_verse_id(book, chapter, verse)
                    assert decode_verse_id(vid) == (book, chapter, verse)

    def test_verse_ref_id(self):
        from scripture.models import VerseRef
        ref = VerseRef(book=43, chapter=3, verse=16)
        assert ref.verse_id == 43003016

    def test_verse_range_ids(self):
        from scripture.models import VerseRange, VerseRef
        vr = VerseRange(
            start=VerseRef(book=1, chapter=1, verse=1),
            end=VerseRef(book=1, chapter=1, verse=3),
        )
        ids = vr.verse_ids()
        assert 1001001 in ids
        assert 1001002 in ids
        assert 1001003 in ids

    def test_verse_model(self):
        from scripture.models import Verse
        v = Verse(
            verse_id=43003016,
            book=43,
            chapter=3,
            verse_num=16,
            text="For God so loved the world...",
            translation="ESV",
            testament="NT",
            genre="gospel",
        )
        assert v.text.startswith("For God")
        assert v.testament == "NT"

    def test_meditation_state_advance(self):
        from scripture.models import MeditationState
        state = MeditationState()
        assert state.verses_meditated == 0
        state.advance(1, 1, 2)
        assert state.current_verse == 2
        assert state.verses_meditated == 1
        assert state.last_meditation is not None

    def test_scripture_query_defaults(self):
        from scripture.models import ScriptureQuery
        q = ScriptureQuery(raw_text="test")
        assert q.intent == "lookup"
        assert q.references == []
        assert q.keywords == []

    def test_cross_reference_model(self):
        from scripture.models import CrossReference
        xref = CrossReference(
            source_verse_id=43003016,
            target_verse_id=45005008,
            reference_type="thematic",
            confidence=0.9,
        )
        assert xref.reference_type == "thematic"
        assert xref.confidence == 0.9

    def test_strongs_entry(self):
        from scripture.models import StrongsEntry
        entry = StrongsEntry(
            strongs_number="H7225",
            language="hebrew",
            lemma="רֵאשִׁית",
            transliteration="reshith",
            gloss="beginning",
        )
        assert entry.language == "hebrew"


# ════════════════════════════════════════════════════════════════════════════
# Parser
# ════════════════════════════════════════════════════════════════════════════


class TestParser:
    def test_parse_single_verse(self):
        from scripture.parser import parse_reference
        result = parse_reference("John 3:16")
        assert result is not None
        assert result.start.book == 43
        assert result.start.chapter == 3
        assert result.start.verse == 16
        assert result.end.verse == 16

    def test_parse_range(self):
        from scripture.parser import parse_reference
        result = parse_reference("Romans 5:1-11")
        assert result is not None
        assert result.start.verse == 1
        assert result.end.verse == 11

    def test_parse_whole_chapter(self):
        from scripture.parser import parse_reference
        result = parse_reference("Genesis 1")
        assert result is not None
        assert result.start.verse == 1
        assert result.end.verse == 999  # sentinel for whole chapter

    def test_parse_multi_chapter_range(self):
        from scripture.parser import parse_reference
        result = parse_reference("Genesis 1:1-2:3")
        assert result is not None
        assert result.start.chapter == 1
        assert result.start.verse == 1
        assert result.end.chapter == 2
        assert result.end.verse == 3

    def test_parse_abbreviation(self):
        from scripture.parser import parse_reference
        result = parse_reference("Rom 8:28")
        assert result is not None
        assert result.start.book == 45

    def test_parse_numbered_book(self):
        from scripture.parser import parse_reference
        result = parse_reference("1 Cor 13:4")
        assert result is not None
        assert result.start.book == 46

    def test_parse_invalid(self):
        from scripture.parser import parse_reference
        assert parse_reference("not a reference") is None

    def test_parse_unknown_book(self):
        from scripture.parser import parse_reference
        assert parse_reference("Hezekiah 1:1") is None

    def test_extract_multiple_references(self):
        from scripture.parser import extract_references
        text = "See John 3:16 and Romans 5:8 for the gospel message."
        refs = extract_references(text)
        assert len(refs) == 2
        assert refs[0].start.book == 43
        assert refs[1].start.book == 45

    def test_extract_no_references(self):
        from scripture.parser import extract_references
        assert extract_references("No references here.") == []

    def test_format_reference(self):
        from scripture.models import VerseRef
        from scripture.parser import format_reference
        ref = VerseRef(book=43, chapter=3, verse=16)
        assert format_reference(ref) == "John 3:16"

    def test_format_reference_chapter_only(self):
        from scripture.models import VerseRef
        from scripture.parser import format_reference
        ref = VerseRef(book=1, chapter=1, verse=0)
        assert format_reference(ref) == "Genesis 1"

    def test_format_range_single(self):
        from scripture.models import VerseRange, VerseRef
        from scripture.parser import format_range
        vr = VerseRange(
            start=VerseRef(book=43, chapter=3, verse=16),
            end=VerseRef(book=43, chapter=3, verse=16),
        )
        assert format_range(vr) == "John 3:16"

    def test_format_range_same_chapter(self):
        from scripture.models import VerseRange, VerseRef
        from scripture.parser import format_range
        vr = VerseRange(
            start=VerseRef(book=45, chapter=5, verse=1),
            end=VerseRef(book=45, chapter=5, verse=11),
        )
        assert format_range(vr) == "Romans 5:1-11"

    def test_format_range_multi_chapter(self):
        from scripture.models import VerseRange, VerseRef
        from scripture.parser import format_range
        vr = VerseRange(
            start=VerseRef(book=1, chapter=1, verse=1),
            end=VerseRef(book=1, chapter=2, verse=3),
        )
        assert format_range(vr) == "Genesis 1:1-2:3"


# ════════════════════════════════════════════════════════════════════════════
# Store
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_store():
    """Create a ScriptureStore backed by a temp file."""
    from scripture.store import ScriptureStore
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = ScriptureStore(db_path=db_path)
    yield store
    store.close()
    Path(db_path).unlink(missing_ok=True)


def _sample_verse(book=43, chapter=3, verse_num=16, text="For God so loved the world"):
    from scripture.models import Verse, encode_verse_id
    return Verse(
        verse_id=encode_verse_id(book, chapter, verse_num),
        book=book,
        chapter=chapter,
        verse_num=verse_num,
        text=text,
        translation="ESV",
        testament="NT",
        genre="gospel",
    )


class TestStore:
    def test_insert_and_get(self, temp_store):
        verse = _sample_verse()
        temp_store.insert_verse(verse)
        result = temp_store.get_verse(43, 3, 16)
        assert result is not None
        assert result.text == "For God so loved the world"

    def test_get_nonexistent(self, temp_store):
        assert temp_store.get_verse(99, 1, 1) is None

    def test_get_verse_by_id(self, temp_store):
        verse = _sample_verse()
        temp_store.insert_verse(verse)
        result = temp_store.get_verse_by_id(43003016)
        assert result is not None
        assert result.book == 43

    def test_bulk_insert(self, temp_store):
        verses = [
            _sample_verse(1, 1, 1, "In the beginning God created the heavens and the earth."),
            _sample_verse(1, 1, 2, "The earth was without form and void."),
            _sample_verse(1, 1, 3, "And God said, Let there be light."),
        ]
        temp_store.insert_verses(verses)
        assert temp_store.count_verses() == 3

    def test_get_chapter(self, temp_store):
        verses = [
            _sample_verse(1, 1, i, f"Verse {i}")
            for i in range(1, 6)
        ]
        temp_store.insert_verses(verses)
        chapter = temp_store.get_chapter(1, 1)
        assert len(chapter) == 5
        assert chapter[0].verse_num == 1

    def test_get_range(self, temp_store):
        from scripture.models import encode_verse_id
        verses = [
            _sample_verse(1, 1, i, f"Verse {i}")
            for i in range(1, 11)
        ]
        temp_store.insert_verses(verses)
        result = temp_store.get_range(
            encode_verse_id(1, 1, 3),
            encode_verse_id(1, 1, 7),
        )
        assert len(result) == 5

    def test_search_text(self, temp_store):
        verses = [
            _sample_verse(43, 3, 16, "For God so loved the world"),
            _sample_verse(43, 3, 17, "For God did not send his Son"),
            _sample_verse(45, 5, 8, "God shows his love for us"),
        ]
        temp_store.insert_verses(verses)
        results = temp_store.search_text("God")
        assert len(results) == 3
        results = temp_store.search_text("loved")
        assert len(results) == 1

    def test_count_verses(self, temp_store):
        assert temp_store.count_verses() == 0
        temp_store.insert_verse(_sample_verse())
        assert temp_store.count_verses() == 1

    def test_get_books(self, temp_store):
        verses = [
            _sample_verse(1, 1, 1, "Genesis verse"),
            _sample_verse(43, 1, 1, "John verse"),
        ]
        temp_store.insert_verses(verses)
        books = temp_store.get_books()
        assert len(books) == 2
        assert books[0]["name"] == "Genesis"
        assert books[1]["name"] == "John"

    def test_cross_references(self, temp_store):
        from scripture.models import CrossReference
        xref = CrossReference(
            source_verse_id=43003016,
            target_verse_id=45005008,
            reference_type="thematic",
            confidence=0.9,
        )
        temp_store.insert_cross_reference(xref)
        results = temp_store.get_cross_references(43003016)
        assert len(results) == 1
        assert results[0].target_verse_id == 45005008

    def test_cross_references_bidirectional(self, temp_store):
        from scripture.models import CrossReference
        xref = CrossReference(
            source_verse_id=43003016,
            target_verse_id=45005008,
        )
        temp_store.insert_cross_reference(xref)
        # Query from target side
        results = temp_store.get_cross_references(45005008)
        assert len(results) == 1

    def test_topics(self, temp_store):
        from scripture.models import Topic
        topic = Topic(
            topic_id="love",
            name="Love",
            description="Biblical concept of love",
            verse_ids=[43003016, 45005008],
        )
        temp_store.insert_topic(topic)
        result = temp_store.get_topic("love")
        assert result is not None
        assert result.name == "Love"
        assert len(result.verse_ids) == 2

    def test_search_topics(self, temp_store):
        from scripture.models import Topic
        temp_store.insert_topic(Topic(topic_id="love", name="Love"))
        temp_store.insert_topic(Topic(topic_id="faith", name="Faith"))
        results = temp_store.search_topics("lov")
        assert len(results) == 1
        assert results[0].name == "Love"

    def test_get_verses_for_topic(self, temp_store):
        from scripture.models import Topic
        verse = _sample_verse()
        temp_store.insert_verse(verse)
        topic = Topic(
            topic_id="love",
            name="Love",
            verse_ids=[verse.verse_id],
        )
        temp_store.insert_topic(topic)
        verses = temp_store.get_verses_for_topic("love")
        assert len(verses) == 1
        assert verses[0].verse_id == verse.verse_id

    def test_strongs(self, temp_store):
        from scripture.models import StrongsEntry
        entry = StrongsEntry(
            strongs_number="G26",
            language="greek",
            lemma="ἀγάπη",
            transliteration="agape",
            gloss="love",
        )
        temp_store.insert_strongs(entry)
        result = temp_store.get_strongs("G26")
        assert result is not None
        assert result.gloss == "love"
        assert temp_store.get_strongs("G9999") is None

    def test_stats(self, temp_store):
        stats = temp_store.stats()
        assert stats["verses"] == 0
        assert stats["cross_references"] == 0
        assert stats["topics"] == 0
        assert stats["strongs_entries"] == 0


# ════════════════════════════════════════════════════════════════════════════
# Memory
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_memory():
    """Create a ScriptureMemory backed by a temp file."""
    from scripture.memory import ScriptureMemory
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    mem = ScriptureMemory(db_path=db_path)
    yield mem
    mem.close()
    Path(db_path).unlink(missing_ok=True)


class TestWorkingMemory:
    def test_focus_and_retrieve(self):
        from scripture.memory import WorkingMemory
        wm = WorkingMemory(capacity=3)
        v1 = _sample_verse(1, 1, 1, "Verse 1")
        v2 = _sample_verse(1, 1, 2, "Verse 2")
        wm.focus(v1)
        wm.focus(v2)
        assert len(wm) == 2
        focused = wm.get_focused()
        assert focused[0].verse_id == v1.verse_id
        assert focused[1].verse_id == v2.verse_id

    def test_capacity_eviction(self):
        from scripture.memory import WorkingMemory
        wm = WorkingMemory(capacity=2)
        v1 = _sample_verse(1, 1, 1, "Verse 1")
        v2 = _sample_verse(1, 1, 2, "Verse 2")
        v3 = _sample_verse(1, 1, 3, "Verse 3")
        wm.focus(v1)
        wm.focus(v2)
        wm.focus(v3)
        assert len(wm) == 2
        assert not wm.is_focused(v1.verse_id)
        assert wm.is_focused(v2.verse_id)
        assert wm.is_focused(v3.verse_id)

    def test_refocus_moves_to_end(self):
        from scripture.memory import WorkingMemory
        wm = WorkingMemory(capacity=3)
        v1 = _sample_verse(1, 1, 1, "Verse 1")
        v2 = _sample_verse(1, 1, 2, "Verse 2")
        wm.focus(v1)
        wm.focus(v2)
        wm.focus(v1)  # Re-focus v1
        focused = wm.get_focused()
        assert focused[-1].verse_id == v1.verse_id

    def test_clear(self):
        from scripture.memory import WorkingMemory
        wm = WorkingMemory()
        wm.focus(_sample_verse())
        wm.clear()
        assert len(wm) == 0


class TestAssociativeMemory:
    def test_meditation_state_persistence(self, temp_memory):
        from scripture.models import MeditationState
        state = temp_memory.associative.get_meditation_state()
        assert state.current_book == 1
        assert state.mode == "sequential"

        state.advance(43, 3, 16)
        state.mode = "thematic"
        temp_memory.associative.save_meditation_state(state)

        loaded = temp_memory.associative.get_meditation_state()
        assert loaded.current_book == 43
        assert loaded.current_chapter == 3
        assert loaded.current_verse == 16
        assert loaded.mode == "thematic"
        assert loaded.verses_meditated == 1

    def test_meditation_log(self, temp_memory):
        temp_memory.associative.log_meditation(43003016, notes="Great verse")
        temp_memory.associative.log_meditation(45005008, notes="Also good")
        history = temp_memory.associative.get_meditation_history(limit=10)
        assert len(history) == 2
        assert history[0]["verse_id"] == 45005008  # most recent first

    def test_meditation_count(self, temp_memory):
        assert temp_memory.associative.meditation_count() == 0
        temp_memory.associative.log_meditation(1001001)
        assert temp_memory.associative.meditation_count() == 1

    def test_insights(self, temp_memory):
        temp_memory.associative.add_insight(
            43003016, "God's love is unconditional", category="theology"
        )
        insights = temp_memory.associative.get_insights(43003016)
        assert len(insights) == 1
        assert insights[0]["category"] == "theology"

    def test_recent_insights(self, temp_memory):
        temp_memory.associative.add_insight(1001001, "Creation narrative")
        temp_memory.associative.add_insight(43003016, "Gospel core")
        recent = temp_memory.associative.get_recent_insights(limit=5)
        assert len(recent) == 2

    def test_duplicate_insight_ignored(self, temp_memory):
        temp_memory.associative.add_insight(43003016, "Same insight")
        temp_memory.associative.add_insight(43003016, "Same insight")
        insights = temp_memory.associative.get_insights(43003016)
        assert len(insights) == 1


class TestScriptureMemory:
    def test_status(self, temp_memory):
        status = temp_memory.status()
        assert "working_memory_items" in status
        assert "meditation_mode" in status
        assert status["working_memory_items"] == 0


# ════════════════════════════════════════════════════════════════════════════
# Meditation Scheduler
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_scheduler():
    """Create a MeditationScheduler backed by temp stores."""
    from scripture.meditation import MeditationScheduler
    from scripture.memory import ScriptureMemory
    from scripture.store import ScriptureStore
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        store_path = f.name
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        mem_path = f.name
    store = ScriptureStore(db_path=store_path)
    memory = ScriptureMemory(db_path=mem_path)
    scheduler = MeditationScheduler(store=store, memory=memory)
    yield scheduler, store, memory
    store.close()
    memory.close()
    Path(store_path).unlink(missing_ok=True)
    Path(mem_path).unlink(missing_ok=True)


class TestMeditationScheduler:
    def test_initial_state(self, temp_scheduler):
        scheduler, _, _ = temp_scheduler
        state = scheduler.state
        assert state.mode == "sequential"
        assert state.current_book == 1

    def test_set_mode(self, temp_scheduler):
        scheduler, _, _ = temp_scheduler
        state = scheduler.set_mode("thematic", theme="love")
        assert state.mode == "thematic"
        assert state.theme == "love"

    def test_set_invalid_mode(self, temp_scheduler):
        scheduler, _, _ = temp_scheduler
        with pytest.raises(ValueError, match="Unknown mode"):
            scheduler.set_mode("invalid")

    def test_next_sequential(self, temp_scheduler):
        scheduler, store, _ = temp_scheduler
        verses = [
            _sample_verse(1, 1, i, f"Genesis 1:{i}")
            for i in range(1, 6)
        ]
        store.insert_verses(verses)
        # State starts at 1:1:1, next should be 1:1:2
        result = scheduler.next_meditation()
        assert result is not None
        assert result.verse_num == 2

    def test_sequential_chapter_advance(self, temp_scheduler):
        scheduler, store, _ = temp_scheduler
        # Only two verses in chapter 1, plus verse 1 of chapter 2
        store.insert_verses([
            _sample_verse(1, 1, 1, "Gen 1:1"),
            _sample_verse(1, 1, 2, "Gen 1:2"),
            _sample_verse(1, 2, 1, "Gen 2:1"),
        ])
        # Start at 1:1:1 → next is 1:1:2
        v = scheduler.next_meditation()
        assert v.verse_num == 2
        # Next should advance to 1:2:1
        v = scheduler.next_meditation()
        assert v is not None
        assert v.chapter == 2
        assert v.verse_num == 1

    def test_current_focus_empty(self, temp_scheduler):
        scheduler, _, _ = temp_scheduler
        assert scheduler.current_focus() is None

    def test_meditate_on(self, temp_scheduler):
        scheduler, store, memory = temp_scheduler
        verse = _sample_verse()
        store.insert_verse(verse)
        scheduler.meditate_on(verse, notes="Reflecting on love")
        assert memory.working.is_focused(verse.verse_id)
        state = scheduler.state
        assert state.verses_meditated == 1

    def test_status(self, temp_scheduler):
        scheduler, _, _ = temp_scheduler
        status = scheduler.status()
        assert "mode" in status
        assert "current_book" in status
        assert "verses_meditated" in status

    def test_history(self, temp_scheduler):
        scheduler, store, _ = temp_scheduler
        verse = _sample_verse()
        store.insert_verse(verse)
        scheduler.meditate_on(verse)
        history = scheduler.history(limit=5)
        assert len(history) == 1

    def test_get_context(self, temp_scheduler):
        scheduler, store, _ = temp_scheduler
        verses = [_sample_verse(1, 1, i, f"Gen 1:{i}") for i in range(1, 6)]
        store.insert_verses(verses)
        ctx = scheduler.get_context(verses[2], before=1, after=1)
        assert len(ctx) == 3

    def test_get_cross_references(self, temp_scheduler):
        from scripture.models import CrossReference
        scheduler, store, _ = temp_scheduler
        v1 = _sample_verse(43, 3, 16, "For God so loved")
        v2 = _sample_verse(45, 5, 8, "God shows his love")
        store.insert_verse(v1)
        store.insert_verse(v2)
        store.insert_cross_reference(CrossReference(
            source_verse_id=v1.verse_id,
            target_verse_id=v2.verse_id,
        ))
        xrefs = scheduler.get_cross_references(v1)
        assert len(xrefs) == 1
        assert xrefs[0].verse_id == v2.verse_id


# ════════════════════════════════════════════════════════════════════════════
# Routes
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def scripture_client(tmp_path):
    """TestClient with isolated scripture stores."""
    from scripture.meditation import MeditationScheduler
    from scripture.memory import ScriptureMemory
    from scripture.store import ScriptureStore

    store = ScriptureStore(db_path=tmp_path / "scripture.db")
    memory = ScriptureMemory(db_path=tmp_path / "memory.db")
    scheduler = MeditationScheduler(store=store, memory=memory)

    # Seed with some verses for route testing
    store.insert_verses([
        _sample_verse(43, 3, 16, "For God so loved the world, that he gave his only Son, that whoever believes in him should not perish but have eternal life."),
        _sample_verse(43, 3, 17, "For God did not send his Son into the world to condemn the world, but in order that the world might be saved through him."),
        _sample_verse(45, 5, 8, "but God shows his love for us in that while we were still sinners, Christ died for us."),
        _sample_verse(1, 1, 1, "In the beginning, God created the heavens and the earth."),
        _sample_verse(1, 1, 2, "The earth was without form and void, and darkness was over the face of the deep."),
        _sample_verse(1, 1, 3, "And God said, Let there be light, and there was light."),
    ])

    with patch("dashboard.routes.scripture.scripture_store", store), \
         patch("dashboard.routes.scripture.scripture_memory", memory), \
         patch("dashboard.routes.scripture.meditation_scheduler", scheduler):
        from dashboard.app import app
        with TestClient(app) as c:
            yield c

    store.close()
    memory.close()


class TestScriptureRoutes:
    def test_scripture_status(self, scripture_client):
        resp = scripture_client.get("/scripture")
        assert resp.status_code == 200
        data = resp.json()
        assert "store" in data
        assert "memory" in data
        assert "meditation" in data

    def test_get_verse(self, scripture_client):
        resp = scripture_client.get("/scripture/verse", params={"ref": "John 3:16"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["reference"] == "John 3:16"
        assert "loved" in data["text"]

    def test_get_verse_range(self, scripture_client):
        resp = scripture_client.get("/scripture/verse", params={"ref": "John 3:16-17"})
        assert resp.status_code == 200
        data = resp.json()
        assert "verses" in data
        assert len(data["verses"]) == 2

    def test_get_verse_bad_ref(self, scripture_client):
        resp = scripture_client.get("/scripture/verse", params={"ref": "not a ref"})
        assert resp.status_code == 400

    def test_get_verse_not_found(self, scripture_client):
        resp = scripture_client.get("/scripture/verse", params={"ref": "Jude 1:25"})
        assert resp.status_code == 404

    def test_get_chapter(self, scripture_client):
        resp = scripture_client.get(
            "/scripture/chapter", params={"book": "Genesis", "chapter": 1}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["book"] == "Genesis"
        assert len(data["verses"]) == 3

    def test_get_chapter_bad_book(self, scripture_client):
        resp = scripture_client.get(
            "/scripture/chapter", params={"book": "FakeBook", "chapter": 1}
        )
        assert resp.status_code == 400

    def test_search(self, scripture_client):
        resp = scripture_client.get("/scripture/search", params={"q": "God"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] > 0

    def test_search_empty(self, scripture_client):
        resp = scripture_client.get("/scripture/search", params={"q": "xyznonexistent"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_meditate_get(self, scripture_client):
        resp = scripture_client.get("/scripture/meditate")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_meditate_post(self, scripture_client):
        resp = scripture_client.post("/scripture/meditate")
        assert resp.status_code == 200
        data = resp.json()
        assert "verse" in data
        assert "status" in data

    def test_set_meditation_mode(self, scripture_client):
        resp = scripture_client.post(
            "/scripture/meditate/mode", params={"mode": "thematic", "theme": "love"}
        )
        assert resp.status_code == 200
        assert resp.json()["mode"] == "thematic"

    def test_set_meditation_mode_invalid(self, scripture_client):
        resp = scripture_client.post(
            "/scripture/meditate/mode", params={"mode": "invalid"}
        )
        assert resp.status_code == 400

    def test_memory_status(self, scripture_client):
        resp = scripture_client.get("/scripture/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert "working_memory_items" in data

    def test_stats(self, scripture_client):
        resp = scripture_client.get("/scripture/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "verses" in data

    def test_ingest(self, scripture_client):
        payload = {
            "verses": [
                {"book": 19, "chapter": 23, "verse_num": 1, "text": "The LORD is my shepherd; I shall not want."},
                {"book": 19, "chapter": 23, "verse_num": 2, "text": "He makes me lie down in green pastures."},
            ]
        }
        resp = scripture_client.post("/scripture/ingest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ingested"] == 2

    def test_ingest_invalid(self, scripture_client):
        resp = scripture_client.post("/scripture/ingest", json={"verses": []})
        assert resp.status_code == 400

    def test_ingest_bad_json(self, scripture_client):
        resp = scripture_client.post(
            "/scripture/ingest",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_xref(self, scripture_client):
        resp = scripture_client.get("/scripture/xref", params={"ref": "John 3:16"})
        assert resp.status_code == 200
        data = resp.json()
        assert "source" in data
        assert "cross_references" in data

    def test_xref_not_found(self, scripture_client):
        resp = scripture_client.get("/scripture/xref", params={"ref": "Jude 1:25"})
        assert resp.status_code == 404
