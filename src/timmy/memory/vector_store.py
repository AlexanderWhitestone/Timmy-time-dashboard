"""Vector store for semantic memory using sqlite-vss.

Provides embedding-based similarity search for the Echo agent
to retrieve relevant context from conversation history.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/swarm.db")

# Simple embedding function using sentence-transformers if available,
# otherwise fall back to keyword-based "pseudo-embeddings"
_model = None
_has_embeddings = None


def _get_model():
    """Lazy-load the embedding model."""
    global _model, _has_embeddings
    if _has_embeddings is False:
        return None
    
    if _model is not None:
        return _model
    
    from config import settings
    # In test mode or low-memory environments, skip embedding model load
    if settings.timmy_skip_embeddings:
        _has_embeddings = False
        return None

    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        _has_embeddings = True
        return _model
    except (ImportError, RuntimeError, Exception):
        # Gracefully fall back if anything goes wrong (e.g. OOM, Bus error)
        _has_embeddings = False
        return None


def _get_embedding_dimension() -> int:
    """Get the dimension of embeddings."""
    model = _get_model()
    if model:
        return model.get_sentence_embedding_dimension()
    return 384  # Default for all-MiniLM-L6-v2


def _compute_embedding(text: str) -> list[float]:
    """Compute embedding vector for text.
    
    Uses sentence-transformers if available, otherwise returns
    a simple hash-based vector for basic similarity.
    """
    model = _get_model()
    if model:
        try:
            return model.encode(text).tolist()
        except Exception:
            pass
    
    # Fallback: simple character n-gram hash embedding
    # Not as good but allows the system to work without heavy deps
    dim = 384
    vec = [0.0] * dim
    text = text.lower()
    
    # Generate character trigram features
    for i in range(len(text) - 2):
        trigram = text[i:i+3]
        hash_val = hash(trigram) % dim
        vec[hash_val] += 1.0
    
    # Normalize
    norm = sum(x*x for x in vec) ** 0.5
    if norm > 0:
        vec = [x/norm for x in vec]
    
    return vec


@dataclass
class MemoryEntry:
    """A memory entry with vector embedding."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""  # The actual text content
    source: str = ""  # Where it came from (agent, user, system)
    context_type: str = "conversation"  # conversation, document, fact, etc.
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[dict] = None
    embedding: Optional[list[float]] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    relevance_score: Optional[float] = None  # Set during search


def _get_conn() -> sqlite3.Connection:
    """Get database connection with vector extension."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # Try to load sqlite-vss extension
    try:
        conn.enable_load_extension(True)
        conn.load_extension("vector0")
        conn.load_extension("vss0")
        _has_vss = True
    except Exception:
        _has_vss = False
    
    # Create tables
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_entries (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            source TEXT NOT NULL,
            context_type TEXT NOT NULL DEFAULT 'conversation',
            agent_id TEXT,
            task_id TEXT,
            session_id TEXT,
            metadata TEXT,
            embedding TEXT,  -- JSON array of floats
            timestamp TEXT NOT NULL
        )
        """
    )
    
    # Create indexes
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_agent ON memory_entries(agent_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_task ON memory_entries(task_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_session ON memory_entries(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_time ON memory_entries(timestamp)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_entries(context_type)"
    )
    
    conn.commit()
    return conn


def store_memory(
    content: str,
    source: str,
    context_type: str = "conversation",
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    compute_embedding: bool = True,
) -> MemoryEntry:
    """Store a memory entry with optional embedding.
    
    Args:
        content: The text content to store
        source: Source of the memory (agent name, user, system)
        context_type: Type of context (conversation, document, fact)
        agent_id: Associated agent ID
        task_id: Associated task ID
        session_id: Session identifier
        metadata: Additional structured data
        compute_embedding: Whether to compute vector embedding
    
    Returns:
        The stored MemoryEntry
    """
    embedding = None
    if compute_embedding:
        embedding = _compute_embedding(content)
    
    entry = MemoryEntry(
        content=content,
        source=source,
        context_type=context_type,
        agent_id=agent_id,
        task_id=task_id,
        session_id=session_id,
        metadata=metadata,
        embedding=embedding,
    )
    
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO memory_entries 
        (id, content, source, context_type, agent_id, task_id, session_id, 
         metadata, embedding, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.id,
            entry.content,
            entry.source,
            entry.context_type,
            entry.agent_id,
            entry.task_id,
            entry.session_id,
            json.dumps(metadata) if metadata else None,
            json.dumps(embedding) if embedding else None,
            entry.timestamp,
        ),
    )
    conn.commit()
    conn.close()
    
    return entry


def search_memories(
    query: str,
    limit: int = 10,
    context_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    min_relevance: float = 0.0,
) -> list[MemoryEntry]:
    """Search for memories by semantic similarity.
    
    Args:
        query: Search query text
        limit: Maximum results
        context_type: Filter by context type
        agent_id: Filter by agent
        session_id: Filter by session
        min_relevance: Minimum similarity score (0-1)
    
    Returns:
        List of MemoryEntry objects sorted by relevance
    """
    query_embedding = _compute_embedding(query)
    
    conn = _get_conn()
    
    # Build query with filters
    conditions = []
    params = []
    
    if context_type:
        conditions.append("context_type = ?")
        params.append(context_type)
    if agent_id:
        conditions.append("agent_id = ?")
        params.append(agent_id)
    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Fetch candidates (we'll do in-memory similarity for now)
    # For production with sqlite-vss, this would use vector similarity index
    query_sql = f"""
        SELECT * FROM memory_entries
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ?
    """
    params.append(limit * 3)  # Get more candidates for ranking
    
    rows = conn.execute(query_sql, params).fetchall()
    conn.close()
    
    # Compute similarity scores
    results = []
    for row in rows:
        entry = MemoryEntry(
            id=row["id"],
            content=row["content"],
            source=row["source"],
            context_type=row["context_type"],
            agent_id=row["agent_id"],
            task_id=row["task_id"],
            session_id=row["session_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
            timestamp=row["timestamp"],
        )
        
        if entry.embedding:
            # Cosine similarity
            score = _cosine_similarity(query_embedding, entry.embedding)
            entry.relevance_score = score
            if score >= min_relevance:
                results.append(entry)
        else:
            # Fallback: check for keyword overlap
            score = _keyword_overlap(query, entry.content)
            entry.relevance_score = score
            if score >= min_relevance:
                results.append(entry)
    
    # Sort by relevance and return top results
    results.sort(key=lambda x: x.relevance_score or 0, reverse=True)
    return results[:limit]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x*y for x, y in zip(a, b))
    norm_a = sum(x*x for x in a) ** 0.5
    norm_b = sum(x*x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_overlap(query: str, content: str) -> float:
    """Simple keyword overlap score as fallback."""
    query_words = set(query.lower().split())
    content_words = set(content.lower().split())
    if not query_words:
        return 0.0
    overlap = len(query_words & content_words)
    return overlap / len(query_words)


def get_memory_context(
    query: str,
    max_tokens: int = 2000,
    **filters
) -> str:
    """Get relevant memory context as formatted text for LLM prompts.
    
    Args:
        query: Search query
        max_tokens: Approximate maximum tokens to return
        **filters: Additional filters (agent_id, session_id, etc.)
    
    Returns:
        Formatted context string for inclusion in prompts
    """
    memories = search_memories(query, limit=20, **filters)
    
    context_parts = []
    total_chars = 0
    max_chars = max_tokens * 4  # Rough approximation
    
    for mem in memories:
        formatted = f"[{mem.source}]: {mem.content}"
        if total_chars + len(formatted) > max_chars:
            break
        context_parts.append(formatted)
        total_chars += len(formatted)
    
    if not context_parts:
        return ""
    
    return "Relevant context from memory:\n" + "\n\n".join(context_parts)


def recall_personal_facts(agent_id: Optional[str] = None) -> list[str]:
    """Recall personal facts about the user or system.
    
    Args:
        agent_id: Optional agent filter
    
    Returns:
        List of fact strings
    """
    conn = _get_conn()
    
    if agent_id:
        rows = conn.execute(
            """
            SELECT content FROM memory_entries
            WHERE context_type = 'fact' AND agent_id = ?
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            (agent_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT content FROM memory_entries
            WHERE context_type = 'fact'
            ORDER BY timestamp DESC
            LIMIT 100
            """,
        ).fetchall()
    
    conn.close()
    return [r["content"] for r in rows]


def recall_personal_facts_with_ids(agent_id: Optional[str] = None) -> list[dict]:
    """Recall personal facts with their IDs for edit/delete operations."""
    conn = _get_conn()
    if agent_id:
        rows = conn.execute(
            "SELECT id, content FROM memory_entries WHERE context_type = 'fact' AND agent_id = ? ORDER BY timestamp DESC LIMIT 100",
            (agent_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, content FROM memory_entries WHERE context_type = 'fact' ORDER BY timestamp DESC LIMIT 100",
        ).fetchall()
    conn.close()
    return [{"id": r["id"], "content": r["content"]} for r in rows]


def update_personal_fact(memory_id: str, new_content: str) -> bool:
    """Update a personal fact's content."""
    conn = _get_conn()
    cursor = conn.execute(
        "UPDATE memory_entries SET content = ? WHERE id = ? AND context_type = 'fact'",
        (new_content, memory_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def store_personal_fact(fact: str, agent_id: Optional[str] = None) -> MemoryEntry:
    """Store a personal fact about the user or system.
    
    Args:
        fact: The fact to store
        agent_id: Associated agent
    
    Returns:
        The stored MemoryEntry
    """
    return store_memory(
        content=fact,
        source="system",
        context_type="fact",
        agent_id=agent_id,
        metadata={"auto_extracted": False},
    )


def delete_memory(memory_id: str) -> bool:
    """Delete a memory entry by ID.
    
    Returns:
        True if deleted, False if not found
    """
    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM memory_entries WHERE id = ?",
        (memory_id,),
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_memory_stats() -> dict:
    """Get statistics about the memory store.
    
    Returns:
        Dict with counts by type, total entries, etc.
    """
    conn = _get_conn()
    
    total = conn.execute(
        "SELECT COUNT(*) as count FROM memory_entries"
    ).fetchone()["count"]
    
    by_type = {}
    rows = conn.execute(
        "SELECT context_type, COUNT(*) as count FROM memory_entries GROUP BY context_type"
    ).fetchall()
    for row in rows:
        by_type[row["context_type"]] = row["count"]
    
    with_embeddings = conn.execute(
        "SELECT COUNT(*) as count FROM memory_entries WHERE embedding IS NOT NULL"
    ).fetchone()["count"]
    
    conn.close()
    
    return {
        "total_entries": total,
        "by_type": by_type,
        "with_embeddings": with_embeddings,
        "has_embedding_model": _has_embeddings,
    }


def prune_memories(older_than_days: int = 90, keep_facts: bool = True) -> int:
    """Delete old memories to manage storage.
    
    Args:
        older_than_days: Delete memories older than this
        keep_facts: Whether to preserve fact-type memories
    
    Returns:
        Number of entries deleted
    """
    from datetime import timedelta
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
    
    conn = _get_conn()
    
    if keep_facts:
        cursor = conn.execute(
            """
            DELETE FROM memory_entries 
            WHERE timestamp < ? AND context_type != 'fact'
            """,
            (cutoff,),
        )
    else:
        cursor = conn.execute(
            "DELETE FROM memory_entries WHERE timestamp < ?",
            (cutoff,),
        )
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    return deleted
