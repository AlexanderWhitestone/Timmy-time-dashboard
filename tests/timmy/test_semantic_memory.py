"""Tests for timmy.semantic_memory — semantic search, chunking, indexing."""

import pytest
from pathlib import Path
from unittest.mock import patch

from timmy.semantic_memory import (
    _simple_hash_embedding,
    embed_text,
    cosine_similarity,
    SemanticMemory,
    MemorySearcher,
    MemoryChunk,
    memory_search,
    _get_embedding_model,
)


class TestSimpleHashEmbedding:
    """Test the fallback hash-based embedding."""

    def test_returns_list_of_floats(self):
        vec = _simple_hash_embedding("hello world")
        assert isinstance(vec, list)
        assert len(vec) == 128
        assert all(isinstance(x, float) for x in vec)

    def test_deterministic(self):
        a = _simple_hash_embedding("same text")
        b = _simple_hash_embedding("same text")
        assert a == b

    def test_different_texts_differ(self):
        a = _simple_hash_embedding("hello world")
        b = _simple_hash_embedding("goodbye universe")
        assert a != b

    def test_normalized(self):
        import math
        vec = _simple_hash_embedding("test normalization")
        magnitude = math.sqrt(sum(x * x for x in vec))
        assert abs(magnitude - 1.0) < 0.01


class TestEmbedText:
    """Test embed_text with fallback."""

    def test_returns_embedding(self):
        # TIMMY_SKIP_EMBEDDINGS=1 in conftest, so uses fallback
        vec = embed_text("test text")
        assert isinstance(vec, list)
        assert len(vec) > 0


class TestCosineSimilarity:
    """Test cosine_similarity function."""

    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 0.0]
        assert cosine_similarity(a, b) == 0.0


class TestSemanticMemory:
    """Test SemanticMemory class."""

    @pytest.fixture
    def mem(self, tmp_path):
        sm = SemanticMemory()
        sm.db_path = tmp_path / "test_semantic.db"
        sm.vault_path = tmp_path / "vault"
        sm.vault_path.mkdir()
        sm._init_db()
        return sm

    def test_init_creates_db(self, mem):
        assert mem.db_path.exists()

    def test_split_into_chunks_short(self, mem):
        text = "Short paragraph."
        chunks = mem._split_into_chunks(text)
        assert len(chunks) == 1
        assert chunks[0] == "Short paragraph."

    def test_split_into_chunks_multiple_paragraphs(self, mem):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = mem._split_into_chunks(text)
        assert len(chunks) == 3

    def test_split_into_chunks_long_paragraph(self, mem):
        text = ". ".join([f"Sentence {i}" for i in range(50)])
        chunks = mem._split_into_chunks(text, max_chunk_size=100)
        assert len(chunks) > 1

    def test_split_empty_text(self, mem):
        assert mem._split_into_chunks("") == []

    def test_index_file(self, mem):
        md_file = mem.vault_path / "test.md"
        md_file.write_text("# Title\n\nThis is a test document with enough content to index properly.\n\nAnother paragraph with more content here.")
        count = mem.index_file(md_file)
        assert count > 0

    def test_index_nonexistent_file(self, mem):
        count = mem.index_file(Path("/nonexistent/file.md"))
        assert count == 0

    def test_index_file_skips_already_indexed(self, mem):
        md_file = mem.vault_path / "cached.md"
        md_file.write_text("# Cached\n\nContent that should only be indexed once if unchanged.")
        count1 = mem.index_file(md_file)
        count2 = mem.index_file(md_file)
        assert count1 > 0
        assert count2 == 0  # Already indexed, same hash

    def test_index_vault(self, mem):
        (mem.vault_path / "a.md").write_text("# File A\n\nContent of file A with some meaningful text here.")
        (mem.vault_path / "b.md").write_text("# File B\n\nContent of file B with different meaningful text.")
        total = mem.index_vault()
        assert total >= 2

    def test_index_vault_skips_handoff(self, mem):
        """Verify handoff files are excluded from indexing."""
        handoff = mem.vault_path / "last-session-handoff.md"
        handoff.write_text("# Handoff\n\nThis should be skipped completely from indexing.")
        real = mem.vault_path / "real.md"
        real.write_text("# Real\n\nThis should be indexed with enough meaningful content.")

        # index_file on the handoff file should NOT skip it
        # (that's only index_vault logic), so test the vault logic directly
        count = mem.index_file(handoff)
        assert count > 0  # index_file indexes everything

        # Wipe and re-test via index_vault
        import sqlite3
        conn = sqlite3.connect(str(mem.db_path))
        conn.execute("DELETE FROM chunks")
        conn.commit()
        conn.close()

        mem.index_vault()
        conn = sqlite3.connect(str(mem.db_path))
        rows = conn.execute("SELECT DISTINCT source FROM chunks").fetchall()
        conn.close()
        sources = [r[0] for r in rows]
        # Only the real file should be indexed, not the handoff
        assert any("real" in s for s in sources)
        assert not any("last-session-handoff" in s for s in sources)

    def test_search_returns_results(self, mem):
        md = mem.vault_path / "searchable.md"
        md.write_text("# Python\n\nPython is a programming language used for web development and data science.")
        mem.index_file(md)

        results = mem.search("programming language")
        assert len(results) > 0
        # Each result is (content, score)
        assert isinstance(results[0], tuple)
        assert len(results[0]) == 2

    def test_search_empty_db(self, mem):
        results = mem.search("anything")
        assert results == []

    def test_get_relevant_context(self, mem):
        md = mem.vault_path / "context.md"
        md.write_text("# Important\n\nThis is very important information about the system architecture.")
        mem.index_file(md)

        ctx = mem.get_relevant_context("architecture")
        # May or may not match depending on hash-based similarity
        assert isinstance(ctx, str)

    def test_get_relevant_context_empty(self, mem):
        assert mem.get_relevant_context("anything") == ""

    def test_stats(self, mem):
        stats = mem.stats()
        assert "total_chunks" in stats
        assert "total_files" in stats
        assert stats["total_chunks"] == 0


class TestMemorySearcher:
    """Test MemorySearcher high-level interface."""

    @pytest.fixture
    def searcher(self, tmp_path):
        ms = MemorySearcher()
        ms.semantic.db_path = tmp_path / "searcher.db"
        ms.semantic.vault_path = tmp_path / "vault"
        ms.semantic.vault_path.mkdir()
        ms.semantic._init_db()
        return ms

    def test_search_semantic_tier(self, searcher):
        results = searcher.search("test query", tiers=["semantic"])
        assert "semantic" in results

    def test_search_defaults_to_semantic(self, searcher):
        results = searcher.search("test")
        assert "semantic" in results

    def test_get_context_for_query_empty(self, searcher):
        ctx = searcher.get_context_for_query("test")
        assert ctx == ""  # Empty DB


class TestMemorySearch:
    """Test module-level memory_search function."""

    def test_no_results(self):
        result = memory_search("something obscure that won't match anything")
        assert isinstance(result, str)

    def test_none_top_k_handled(self):
        result = memory_search("test", top_k=None)
        assert isinstance(result, str)


class TestMemoryChunk:
    """Test MemoryChunk dataclass."""

    def test_create(self):
        chunk = MemoryChunk(
            id="c1",
            source="/path/to/file.md",
            content="chunk text",
            embedding=[0.1, 0.2],
            created_at="2026-03-06",
        )
        assert chunk.id == "c1"
        assert chunk.content == "chunk text"
