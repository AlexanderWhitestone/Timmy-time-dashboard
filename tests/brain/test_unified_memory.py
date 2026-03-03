"""Tests for brain.memory — Unified Memory interface.

Tests the local SQLite backend (default). rqlite tests are integration-only.

TDD: These tests define the contract that UnifiedMemory must fulfill.
Any substrate that reads/writes memory goes through this interface.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from brain.memory import UnifiedMemory, get_memory


@pytest.fixture
def memory(tmp_path):
    """Create a UnifiedMemory instance with a temp database."""
    db_path = tmp_path / "test_brain.db"
    return UnifiedMemory(db_path=db_path, source="test", use_rqlite=False)


# ── Initialization ────────────────────────────────────────────────────────────


class TestUnifiedMemoryInit:
    """Validate database initialization and schema."""

    def test_creates_database_file(self, tmp_path):
        """Database file should be created on init."""
        db_path = tmp_path / "test.db"
        assert not db_path.exists()
        UnifiedMemory(db_path=db_path, use_rqlite=False)
        assert db_path.exists()

    def test_creates_parent_directories(self, tmp_path):
        """Should create parent dirs if they don't exist."""
        db_path = tmp_path / "deep" / "nested" / "brain.db"
        UnifiedMemory(db_path=db_path, use_rqlite=False)
        assert db_path.exists()

    def test_schema_has_memories_table(self, memory):
        """Schema should include memories table."""
        conn = memory._get_conn()
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
            )
            assert cursor.fetchone() is not None
        finally:
            conn.close()

    def test_schema_has_facts_table(self, memory):
        """Schema should include facts table."""
        conn = memory._get_conn()
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='facts'"
            )
            assert cursor.fetchone() is not None
        finally:
            conn.close()

    def test_schema_version_recorded(self, memory):
        """Schema version should be recorded."""
        conn = memory._get_conn()
        try:
            cursor = conn.execute("SELECT version FROM brain_schema_version")
            row = cursor.fetchone()
            assert row is not None
            assert row["version"] == 1
        finally:
            conn.close()

    def test_idempotent_init(self, tmp_path):
        """Initializing twice on the same DB should not error."""
        db_path = tmp_path / "test.db"
        m1 = UnifiedMemory(db_path=db_path, use_rqlite=False)
        m1.remember_sync("first memory")
        m2 = UnifiedMemory(db_path=db_path, use_rqlite=False)
        # Should not lose data
        results = m2.recall_sync("first")
        assert len(results) >= 1


# ── Remember (Sync) ──────────────────────────────────────────────────────────


class TestRememberSync:
    """Test synchronous memory storage."""

    def test_remember_returns_id(self, memory):
        """remember_sync should return dict with id and status."""
        result = memory.remember_sync("User prefers dark mode")
        assert "id" in result
        assert result["status"] == "stored"
        assert result["id"] is not None

    def test_remember_stores_content(self, memory):
        """Stored content should be retrievable."""
        memory.remember_sync("The sky is blue")
        results = memory.recall_sync("sky")
        assert len(results) >= 1
        assert "sky" in results[0]["content"].lower()

    def test_remember_with_tags(self, memory):
        """Tags should be stored and retrievable."""
        memory.remember_sync("Dark mode enabled", tags=["preference", "ui"])
        conn = memory._get_conn()
        try:
            row = conn.execute("SELECT tags FROM memories WHERE content = ?", ("Dark mode enabled",)).fetchone()
            tags = json.loads(row["tags"])
            assert "preference" in tags
            assert "ui" in tags
        finally:
            conn.close()

    def test_remember_with_metadata(self, memory):
        """Metadata should be stored as JSON."""
        memory.remember_sync("Test", metadata={"key": "value", "count": 42})
        conn = memory._get_conn()
        try:
            row = conn.execute("SELECT metadata FROM memories WHERE content = 'Test'").fetchone()
            meta = json.loads(row["metadata"])
            assert meta["key"] == "value"
            assert meta["count"] == 42
        finally:
            conn.close()

    def test_remember_with_custom_source(self, memory):
        """Source should default to self.source but be overridable."""
        memory.remember_sync("From timmy", source="timmy")
        memory.remember_sync("From user", source="user")
        conn = memory._get_conn()
        try:
            rows = conn.execute("SELECT source FROM memories ORDER BY id").fetchall()
            sources = [r["source"] for r in rows]
            assert "timmy" in sources
            assert "user" in sources
        finally:
            conn.close()

    def test_remember_default_source(self, memory):
        """Default source should be the one set at init."""
        memory.remember_sync("Default source test")
        conn = memory._get_conn()
        try:
            row = conn.execute("SELECT source FROM memories").fetchone()
            assert row["source"] == "test"  # set in fixture
        finally:
            conn.close()

    def test_remember_multiple(self, memory):
        """Multiple memories should be stored independently."""
        for i in range(5):
            memory.remember_sync(f"Memory number {i}")
        conn = memory._get_conn()
        try:
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            assert count == 5
        finally:
            conn.close()


# ── Recall (Sync) ─────────────────────────────────────────────────────────────


class TestRecallSync:
    """Test synchronous memory recall (keyword fallback)."""

    def test_recall_finds_matching(self, memory):
        """Recall should find memories matching the query."""
        memory.remember_sync("Bitcoin price is rising")
        memory.remember_sync("Weather is sunny today")
        results = memory.recall_sync("Bitcoin")
        assert len(results) >= 1
        assert "Bitcoin" in results[0]["content"]

    def test_recall_low_score_for_irrelevant(self, memory):
        """Recall should return low scores for irrelevant queries.

        Note: Semantic search may still return results (embeddings always
        have *some* similarity), but scores should be low for unrelated content.
        Keyword fallback returns nothing if no substring match.
        """
        memory.remember_sync("Bitcoin price is rising fast")
        results = memory.recall_sync("underwater basket weaving")
        if results:
            # If semantic search returned something, score should be low
            assert results[0]["score"] < 0.7, (
                f"Expected low score for irrelevant query, got {results[0]['score']}"
            )

    def test_recall_respects_limit(self, memory):
        """Recall should respect the limit parameter."""
        for i in range(10):
            memory.remember_sync(f"Bitcoin memory {i}")
        results = memory.recall_sync("Bitcoin", limit=3)
        assert len(results) <= 3

    def test_recall_filters_by_source(self, memory):
        """Recall should filter by source when specified."""
        memory.remember_sync("From timmy", source="timmy")
        memory.remember_sync("From user about timmy", source="user")
        results = memory.recall_sync("timmy", sources=["user"])
        assert all(r["source"] == "user" for r in results)

    def test_recall_returns_score(self, memory):
        """Recall results should include a score."""
        memory.remember_sync("Test memory for scoring")
        results = memory.recall_sync("Test")
        assert len(results) >= 1
        assert "score" in results[0]


# ── Facts ─────────────────────────────────────────────────────────────────────


class TestFacts:
    """Test long-term fact storage."""

    def test_store_fact_returns_id(self, memory):
        """store_fact_sync should return dict with id and status."""
        result = memory.store_fact_sync("user_preference", "Prefers dark mode")
        assert "id" in result
        assert result["status"] == "stored"

    def test_get_facts_by_category(self, memory):
        """get_facts_sync should filter by category."""
        memory.store_fact_sync("user_preference", "Likes dark mode")
        memory.store_fact_sync("user_fact", "Lives in Texas")
        prefs = memory.get_facts_sync(category="user_preference")
        assert len(prefs) == 1
        assert "dark mode" in prefs[0]["content"]

    def test_get_facts_by_query(self, memory):
        """get_facts_sync should support keyword search."""
        memory.store_fact_sync("user_preference", "Likes dark mode")
        memory.store_fact_sync("user_preference", "Prefers Bitcoin")
        results = memory.get_facts_sync(query="Bitcoin")
        assert len(results) == 1
        assert "Bitcoin" in results[0]["content"]

    def test_fact_access_count_increments(self, memory):
        """Accessing a fact should increment its access_count."""
        memory.store_fact_sync("test_cat", "Test fact")
        # First access — count starts at 0, then gets incremented
        facts = memory.get_facts_sync(category="test_cat")
        first_count = facts[0]["access_count"]
        # Second access — count should be higher
        facts = memory.get_facts_sync(category="test_cat")
        second_count = facts[0]["access_count"]
        assert second_count > first_count, (
            f"Access count should increment: {first_count} -> {second_count}"
        )

    def test_fact_confidence_ordering(self, memory):
        """Facts should be ordered by confidence (highest first)."""
        memory.store_fact_sync("cat", "Low confidence fact", confidence=0.3)
        memory.store_fact_sync("cat", "High confidence fact", confidence=0.9)
        facts = memory.get_facts_sync(category="cat")
        assert facts[0]["confidence"] > facts[1]["confidence"]


# ── Recent Memories ───────────────────────────────────────────────────────────


class TestRecentSync:
    """Test recent memory retrieval."""

    def test_get_recent_returns_recent(self, memory):
        """get_recent_sync should return recently stored memories."""
        memory.remember_sync("Just happened")
        results = memory.get_recent_sync(hours=1, limit=10)
        assert len(results) >= 1
        assert "Just happened" in results[0]["content"]

    def test_get_recent_respects_limit(self, memory):
        """get_recent_sync should respect limit."""
        for i in range(10):
            memory.remember_sync(f"Recent {i}")
        results = memory.get_recent_sync(hours=1, limit=3)
        assert len(results) <= 3

    def test_get_recent_filters_by_source(self, memory):
        """get_recent_sync should filter by source."""
        memory.remember_sync("From timmy", source="timmy")
        memory.remember_sync("From user", source="user")
        results = memory.get_recent_sync(hours=1, sources=["timmy"])
        assert all(r["source"] == "timmy" for r in results)


# ── Stats ─────────────────────────────────────────────────────────────────────


class TestStats:
    """Test memory statistics."""

    def test_stats_returns_counts(self, memory):
        """get_stats should return correct counts."""
        memory.remember_sync("Memory 1")
        memory.remember_sync("Memory 2")
        memory.store_fact_sync("cat", "Fact 1")
        stats = memory.get_stats()
        assert stats["memory_count"] == 2
        assert stats["fact_count"] == 1
        assert stats["backend"] == "local_sqlite"

    def test_stats_empty_db(self, memory):
        """get_stats should work on empty database."""
        stats = memory.get_stats()
        assert stats["memory_count"] == 0
        assert stats["fact_count"] == 0


# ── Identity Integration ─────────────────────────────────────────────────────


class TestIdentityIntegration:
    """Identity system removed — stubs return empty strings."""

    def test_get_identity_returns_empty(self, memory):
        assert memory.get_identity() == ""

    def test_get_identity_for_prompt_returns_empty(self, memory):
        assert memory.get_identity_for_prompt() == ""


# ── Singleton ─────────────────────────────────────────────────────────────────


class TestSingleton:
    """Test the module-level get_memory() singleton."""

    def test_get_memory_returns_instance(self):
        """get_memory() should return a UnifiedMemory instance."""
        import brain.memory as mem_module

        # Reset singleton for test isolation
        mem_module._default_memory = None
        m = get_memory()
        assert isinstance(m, UnifiedMemory)

    def test_get_memory_returns_same_instance(self):
        """get_memory() should return the same instance on repeated calls."""
        import brain.memory as mem_module

        mem_module._default_memory = None
        m1 = get_memory()
        m2 = get_memory()
        assert m1 is m2


# ── Async Interface ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAsyncInterface:
    """Test async wrappers (which delegate to sync for local SQLite)."""

    async def test_async_remember(self, memory):
        """Async remember should work."""
        result = await memory.remember("Async memory test")
        assert result["status"] == "stored"

    async def test_async_recall(self, memory):
        """Async recall should work."""
        await memory.remember("Async recall target")
        results = await memory.recall("Async recall")
        assert len(results) >= 1

    async def test_async_store_fact(self, memory):
        """Async store_fact should work."""
        result = await memory.store_fact("test", "Async fact")
        assert result["status"] == "stored"

    async def test_async_get_facts(self, memory):
        """Async get_facts should work."""
        await memory.store_fact("test", "Async fact retrieval")
        facts = await memory.get_facts(category="test")
        assert len(facts) >= 1

    async def test_async_get_recent(self, memory):
        """Async get_recent should work."""
        await memory.remember("Recent async memory")
        results = await memory.get_recent(hours=1)
        assert len(results) >= 1

    async def test_async_get_context(self, memory):
        """Async get_context should return formatted context."""
        await memory.remember("Context test memory")
        context = await memory.get_context("test")
        assert isinstance(context, str)
        assert len(context) > 0
