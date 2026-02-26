"""Tests for vector store (semantic memory) system."""

import pytest
from memory.vector_store import (
    store_memory,
    search_memories,
    get_memory_context,
    recall_personal_facts,
    store_personal_fact,
    delete_memory,
    get_memory_stats,
    prune_memories,
    _cosine_similarity,
    _keyword_overlap,
)


class TestVectorStore:
    """Test suite for vector store functionality."""

    def test_store_simple_memory(self):
        """Test storing a basic memory entry."""
        entry = store_memory(
            content="This is a test memory",
            source="test_agent",
            context_type="conversation",
        )
        
        assert entry.content == "This is a test memory"
        assert entry.source == "test_agent"
        assert entry.context_type == "conversation"
        assert entry.id is not None
        assert entry.timestamp is not None
    
    def test_store_memory_with_metadata(self):
        """Test storing memory with metadata."""
        entry = store_memory(
            content="Memory with metadata",
            source="user",
            context_type="fact",
            agent_id="agent-001",
            task_id="task-123",
            session_id="session-456",
            metadata={"importance": "high", "tags": ["test"]},
        )
        
        assert entry.agent_id == "agent-001"
        assert entry.task_id == "task-123"
        assert entry.session_id == "session-456"
        assert entry.metadata == {"importance": "high", "tags": ["test"]}
    
    def test_search_memories_basic(self):
        """Test basic memory search."""
        # Store some memories
        store_memory("Bitcoin is a decentralized currency", source="user")
        store_memory("Lightning Network enables fast payments", source="user")
        store_memory("Python is a programming language", source="user")
        
        # Search for Bitcoin-related memories
        results = search_memories("cryptocurrency", limit=5)
        
        # Should find at least one relevant result
        assert len(results) > 0
        # Check that results have relevance scores
        assert all(r.relevance_score is not None for r in results)
    
    def test_search_with_filters(self):
        """Test searching with filters."""
        # Store memories with different types
        store_memory(
            "Conversation about AI",
            source="user",
            context_type="conversation",
            agent_id="agent-1",
        )
        store_memory(
            "Fact: AI stands for artificial intelligence",
            source="system",
            context_type="fact",
            agent_id="agent-1",
        )
        store_memory(
            "Another conversation",
            source="user",
            context_type="conversation",
            agent_id="agent-2",
        )
        
        # Filter by context type
        facts = search_memories("AI", context_type="fact", limit=5)
        assert all(f.context_type == "fact" for f in facts)
        
        # Filter by agent
        agent1_memories = search_memories("conversation", agent_id="agent-1", limit=5)
        assert all(m.agent_id == "agent-1" for m in agent1_memories)
    
    def test_get_memory_context(self):
        """Test getting formatted memory context."""
        # Store memories
        store_memory("Important fact about the project", source="user")
        store_memory("Another relevant detail", source="agent")
        
        # Get context
        context = get_memory_context("project details", max_tokens=500)
        
        assert isinstance(context, str)
        assert len(context) > 0
        assert "Relevant context from memory:" in context
    
    def test_personal_facts(self):
        """Test storing and recalling personal facts."""
        # Store a personal fact
        fact = store_personal_fact("User prefers dark mode", agent_id="agent-1")
        
        assert fact.context_type == "fact"
        assert fact.content == "User prefers dark mode"
        
        # Recall facts
        facts = recall_personal_facts(agent_id="agent-1")
        assert "User prefers dark mode" in facts
    
    def test_delete_memory(self):
        """Test deleting a memory entry."""
        # Create a memory
        entry = store_memory("To be deleted", source="test")
        
        # Delete it
        deleted = delete_memory(entry.id)
        assert deleted is True
        
        # Verify it's gone (search shouldn't find it)
        results = search_memories("To be deleted", limit=10)
        assert not any(r.id == entry.id for r in results)
        
        # Deleting non-existent should return False
        deleted_again = delete_memory(entry.id)
        assert deleted_again is False
    
    def test_get_memory_stats(self):
        """Test memory statistics."""
        stats = get_memory_stats()
        
        assert "total_entries" in stats
        assert "by_type" in stats
        assert "with_embeddings" in stats
        assert "has_embedding_model" in stats
        assert isinstance(stats["total_entries"], int)
    
    def test_prune_memories(self):
        """Test pruning old memories."""
        # This just verifies the function works without error
        # (we don't want to delete test data)
        count = prune_memories(older_than_days=365, keep_facts=True)
        assert isinstance(count, int)


class TestVectorStoreUtils:
    """Test utility functions."""
    
    def test_cosine_similarity_identical(self):
        """Test cosine similarity of identical vectors."""
        vec = [1.0, 0.0, 0.0]
        similarity = _cosine_similarity(vec, vec)
        assert similarity == pytest.approx(1.0)
    
    def test_cosine_similarity_orthogonal(self):
        """Test cosine similarity of orthogonal vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        similarity = _cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(0.0)
    
    def test_cosine_similarity_opposite(self):
        """Test cosine similarity of opposite vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]
        similarity = _cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(-1.0)
    
    def test_cosine_similarity_zero_vector(self):
        """Test cosine similarity with zero vector."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 0.0, 0.0]
        similarity = _cosine_similarity(vec1, vec2)
        assert similarity == 0.0
    
    def test_keyword_overlap_exact(self):
        """Test keyword overlap with exact match."""
        query = "bitcoin lightning"
        content = "bitcoin lightning network"
        overlap = _keyword_overlap(query, content)
        assert overlap == 1.0
    
    def test_keyword_overlap_partial(self):
        """Test keyword overlap with partial match."""
        query = "bitcoin lightning"
        content = "bitcoin is great"
        overlap = _keyword_overlap(query, content)
        assert overlap == 0.5
    
    def test_keyword_overlap_none(self):
        """Test keyword overlap with no match."""
        query = "bitcoin"
        content = "completely different topic"
        overlap = _keyword_overlap(query, content)
        assert overlap == 0.0


class TestVectorStoreIntegration:
    """Integration tests for vector store workflow."""
    
    def test_memory_workflow(self):
        """Test complete memory workflow: store -> search -> retrieve."""
        # Store memories
        store_memory(
            "The project deadline is next Friday",
            source="user",
            context_type="fact",
            session_id="session-1",
        )
        store_memory(
            "We need to implement the payment system",
            source="user",
            context_type="conversation",
            session_id="session-1",
        )
        store_memory(
            "The database schema needs updating",
            source="agent",
            context_type="conversation",
            session_id="session-1",
        )
        
        # Search for deadline-related memories
        results = search_memories("when is the deadline", limit=5)
        
        # Should find the deadline memory
        assert len(results) > 0
        # Check that the most relevant result contains "deadline"
        assert any("deadline" in r.content.lower() for r in results[:3])
        
        # Get context for a prompt
        context = get_memory_context("project timeline", session_id="session-1")
        assert "deadline" in context.lower() or "implement" in context.lower()
    
    def test_embedding_vs_keyword_fallback(self):
        """Test that the system works with or without embedding model."""
        stats = get_memory_stats()
        
        # Store a memory
        entry = store_memory(
            "Testing embedding functionality",
            source="test",
            compute_embedding=True,
        )
        
        # Should have embedding (even if it's fallback)
        assert entry.embedding is not None
        
        # Search should work regardless
        results = search_memories("embedding test", limit=5)
        assert len(results) > 0
