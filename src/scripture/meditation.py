"""Meditation scheduler — automated scripture engagement workflows.

Provides background meditation capabilities for the "always on its mind"
requirement.  Supports three modes:

- **Sequential**: book-by-book progression through the Bible
- **Thematic**: topical exploration guided by Nave's-style index
- **Lectionary**: cyclical reading patterns following liturgical calendars

The scheduler integrates with the ScriptureMemory system to persist
progress and working memory state across restarts.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Optional

from scripture.constants import BOOK_BY_ID, BOOKS
from scripture.memory import ScriptureMemory, scripture_memory
from scripture.models import MeditationState, Verse, decode_verse_id, encode_verse_id
from scripture.store import ScriptureStore, scripture_store

logger = logging.getLogger(__name__)


class MeditationScheduler:
    """Orchestrates automated meditation workflows.

    Usage::

        from scripture.meditation import meditation_scheduler

        # Advance to the next verse in sequence
        result = meditation_scheduler.next_meditation()

        # Get the current meditation focus
        current = meditation_scheduler.current_focus()
    """

    def __init__(
        self,
        store: ScriptureStore | None = None,
        memory: ScriptureMemory | None = None,
    ) -> None:
        self._store = store or scripture_store
        self._memory = memory or scripture_memory

    @property
    def state(self) -> MeditationState:
        return self._memory.associative.get_meditation_state()

    def set_mode(self, mode: str, theme: Optional[str] = None) -> MeditationState:
        """Change the meditation mode (sequential / thematic / lectionary)."""
        state = self.state
        if mode not in ("sequential", "thematic", "lectionary"):
            raise ValueError(f"Unknown mode: {mode}")
        state.mode = mode
        state.theme = theme
        self._memory.associative.save_meditation_state(state)
        return state

    def current_focus(self) -> Optional[Verse]:
        """Return the verse currently in meditation focus."""
        state = self.state
        return self._store.get_verse(
            state.current_book, state.current_chapter, state.current_verse
        )

    def next_meditation(self) -> Optional[Verse]:
        """Advance to the next verse and return it.

        Dispatches to the appropriate strategy based on current mode.
        """
        state = self.state
        if state.mode == "thematic":
            return self._next_thematic(state)
        if state.mode == "lectionary":
            return self._next_lectionary(state)
        return self._next_sequential(state)

    def meditate_on(self, verse: Verse, notes: str = "") -> None:
        """Record meditation on a specific verse and bring into focus."""
        self._memory.working.focus(verse)
        self._memory.associative.log_meditation(
            verse.verse_id, notes=notes, mode=self.state.mode
        )
        state = self.state
        state.advance(verse.book, verse.chapter, verse.verse_num)
        self._memory.associative.save_meditation_state(state)

    def get_context(self, verse: Verse, before: int = 2, after: int = 2) -> list[Verse]:
        """Retrieve surrounding verses for contextual meditation."""
        start_id = encode_verse_id(verse.book, verse.chapter, max(1, verse.verse_num - before))
        end_id = encode_verse_id(verse.book, verse.chapter, verse.verse_num + after)
        return self._store.get_range(start_id, end_id)

    def get_cross_references(self, verse: Verse) -> list[Verse]:
        """Retrieve cross-referenced verses for expanded meditation."""
        xrefs = self._store.get_cross_references(verse.verse_id)
        results = []
        for xref in xrefs:
            target_id = (
                xref.target_verse_id
                if xref.source_verse_id == verse.verse_id
                else xref.source_verse_id
            )
            target = self._store.get_verse_by_id(target_id)
            if target:
                results.append(target)
        return results

    def history(self, limit: int = 20) -> list[dict]:
        """Return recent meditation history."""
        return self._memory.associative.get_meditation_history(limit=limit)

    def status(self) -> dict:
        """Return meditation scheduler status."""
        state = self.state
        current = self.current_focus()
        book_info = BOOK_BY_ID.get(state.current_book)
        return {
            "mode": state.mode,
            "theme": state.theme,
            "current_book": book_info.name if book_info else f"Book {state.current_book}",
            "current_chapter": state.current_chapter,
            "current_verse": state.current_verse,
            "current_text": current.text if current else None,
            "verses_meditated": state.verses_meditated,
            "last_meditation": state.last_meditation,
        }

    # ── Private strategies ───────────────────────────────────────────────

    def _next_sequential(self, state: MeditationState) -> Optional[Verse]:
        """Sequential mode: advance verse-by-verse through the Bible."""
        book = state.current_book
        chapter = state.current_chapter
        verse_num = state.current_verse + 1

        # Try next verse in same chapter
        verse = self._store.get_verse(book, chapter, verse_num)
        if verse:
            self.meditate_on(verse)
            return verse

        # Try next chapter
        chapter += 1
        verse_num = 1
        verse = self._store.get_verse(book, chapter, verse_num)
        if verse:
            self.meditate_on(verse)
            return verse

        # Try next book
        book += 1
        if book > 66:
            book = 1  # Wrap around to Genesis
        chapter = 1
        verse_num = 1
        verse = self._store.get_verse(book, chapter, verse_num)
        if verse:
            self.meditate_on(verse)
            return verse

        return None

    def _next_thematic(self, state: MeditationState) -> Optional[Verse]:
        """Thematic mode: retrieve verses related to current theme."""
        if not state.theme:
            # Fall back to sequential if no theme set
            return self._next_sequential(state)

        topics = self._store.search_topics(state.theme, limit=1)
        if not topics:
            return self._next_sequential(state)

        verses = self._store.get_verses_for_topic(topics[0].topic_id)
        if not verses:
            return self._next_sequential(state)

        # Pick the next un-meditated verse (or random if all visited)
        history_ids = {
            e["verse_id"]
            for e in self._memory.associative.get_meditation_history(limit=1000)
        }
        for v in verses:
            if v.verse_id not in history_ids:
                self.meditate_on(v)
                return v

        # All verses in topic visited; pick a random one
        chosen = random.choice(verses)
        self.meditate_on(chosen)
        return chosen

    def _next_lectionary(self, state: MeditationState) -> Optional[Verse]:
        """Lectionary mode: placeholder — rotates through key passages.

        A full lectionary implementation would integrate the Revised Common
        Lectionary or similar.  This simplified version cycles through
        thematically significant passages.
        """
        # Simplified: just advance sequentially for now
        return self._next_sequential(state)


# Module-level singleton
meditation_scheduler = MeditationScheduler()
