"""Unified memory interface for Timmy.

One API, two backends:
- **Local SQLite** (default) — works immediately, no setup
- **Distributed rqlite** — same API, replicated across Tailscale devices

Every module that needs to store or recall memory uses this interface.
No more fragmented SQLite databases scattered across the codebase.

Usage:
    from brain.memory import UnifiedMemory

    memory = UnifiedMemory()  # auto-detects backend

    # Store
    await memory.remember("User prefers dark mode", tags=["preference"])
    memory.remember_sync("User prefers dark mode", tags=["preference"])

    # Recall
    results = await memory.recall("what does the user prefer?")
    results = memory.recall_sync("what does the user prefer?")

    # Facts
    await memory.store_fact("user_preference", "Prefers dark mode")
    facts = await memory.get_facts("user_preference")

    # Identity
    identity = memory.get_identity()

    # Context for prompt
    context = await memory.get_context("current user question")
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default paths
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "brain.db"

# Schema version for migrations
_SCHEMA_VERSION = 1


def _get_db_path() -> Path:
    """Get the brain database path from env or default."""
    env_path = os.environ.get("BRAIN_DB_PATH")
    if env_path:
        return Path(env_path)
    return _DEFAULT_DB_PATH


class UnifiedMemory:
    """Unified memory interface for Timmy.

    Provides a single API for all memory operations. Defaults to local
    SQLite. When rqlite is available (detected via RQLITE_URL env var),
    delegates to BrainClient for distributed operation.

    The interface is the same. The substrate is disposable.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        source: str = "timmy",
        use_rqlite: Optional[bool] = None,
    ):
        self.db_path = db_path or _get_db_path()
        self.source = source
        self._embedder = None
        self._rqlite_client = None

        # Auto-detect: use rqlite if RQLITE_URL is set, otherwise local SQLite
        if use_rqlite is None:
            use_rqlite = bool(os.environ.get("RQLITE_URL"))
        self._use_rqlite = use_rqlite

        if not self._use_rqlite:
            self._init_local_db()

    # ──────────────────────────────────────────────────────────────────────
    # Local SQLite Setup
    # ──────────────────────────────────────────────────────────────────────

    def _init_local_db(self) -> None:
        """Initialize local SQLite database with schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.executescript(_LOCAL_SCHEMA)
            conn.commit()
            logger.info("Brain local DB initialized at %s", self.db_path)
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a SQLite connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _get_embedder(self):
        """Lazy-load the embedding model."""
        if self._embedder is None:
            try:
                from brain.embeddings import LocalEmbedder
                self._embedder = LocalEmbedder()
            except ImportError:
                logger.warning("sentence-transformers not available — semantic search disabled")
                self._embedder = None
        return self._embedder

    # ──────────────────────────────────────────────────────────────────────
    # rqlite Delegation
    # ──────────────────────────────────────────────────────────────────────

    def _get_rqlite_client(self):
        """Lazy-load the rqlite BrainClient."""
        if self._rqlite_client is None:
            from brain.client import BrainClient
            self._rqlite_client = BrainClient()
        return self._rqlite_client

    # ──────────────────────────────────────────────────────────────────────
    # Core Memory Operations
    # ──────────────────────────────────────────────────────────────────────

    async def remember(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a memory.

        Args:
            content: Text content to remember.
            tags: Optional list of tags for categorization.
            source: Source identifier (defaults to self.source).
            metadata: Additional JSON-serializable metadata.

        Returns:
            Dict with 'id' and 'status'.
        """
        if self._use_rqlite:
            client = self._get_rqlite_client()
            return await client.remember(content, tags, source or self.source, metadata)

        return self.remember_sync(content, tags, source, metadata)

    def remember_sync(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a memory (synchronous, local SQLite only).

        Args:
            content: Text content to remember.
            tags: Optional list of tags.
            source: Source identifier.
            metadata: Additional metadata.

        Returns:
            Dict with 'id' and 'status'.
        """
        now = datetime.now(timezone.utc).isoformat()
        embedding_bytes = None

        embedder = self._get_embedder()
        if embedder is not None:
            try:
                embedding_bytes = embedder.encode_single(content)
            except Exception as e:
                logger.warning("Embedding failed, storing without vector: %s", e)

        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT INTO memories (content, embedding, source, tags, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    content,
                    embedding_bytes,
                    source or self.source,
                    json.dumps(tags or []),
                    json.dumps(metadata or {}),
                    now,
                ),
            )
            conn.commit()
            memory_id = cursor.lastrowid
            logger.debug("Stored memory %s: %s", memory_id, content[:50])
            return {"id": memory_id, "status": "stored"}
        finally:
            conn.close()

    async def recall(
        self,
        query: str,
        limit: int = 5,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search for memories.

        If embeddings are available, uses cosine similarity.
        Falls back to keyword search if no embedder.

        Args:
            query: Search query text.
            limit: Max results to return.
            sources: Filter by source(s).

        Returns:
            List of memory dicts with 'content', 'source', 'score'.
        """
        if self._use_rqlite:
            client = self._get_rqlite_client()
            return await client.recall(query, limit, sources)

        return self.recall_sync(query, limit, sources)

    def recall_sync(
        self,
        query: str,
        limit: int = 5,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search (synchronous, local SQLite).

        Uses numpy dot product for cosine similarity when embeddings
        are available. Falls back to LIKE-based keyword search.
        """
        embedder = self._get_embedder()

        if embedder is not None:
            return self._recall_semantic(query, limit, sources, embedder)
        return self._recall_keyword(query, limit, sources)

    def _recall_semantic(
        self,
        query: str,
        limit: int,
        sources: Optional[List[str]],
        embedder,
    ) -> List[Dict[str, Any]]:
        """Vector similarity search over local SQLite."""
        import numpy as np

        try:
            query_vec = embedder.encode(query)
            if len(query_vec.shape) > 1:
                query_vec = query_vec[0]
        except Exception as e:
            logger.warning("Query embedding failed, falling back to keyword: %s", e)
            return self._recall_keyword(query, limit, sources)

        conn = self._get_conn()
        try:
            sql = "SELECT id, content, embedding, source, tags, metadata, created_at FROM memories WHERE embedding IS NOT NULL"
            params: list = []

            if sources:
                placeholders = ",".join(["?"] * len(sources))
                sql += f" AND source IN ({placeholders})"
                params.extend(sources)

            rows = conn.execute(sql, params).fetchall()

            # Compute similarities
            scored = []
            for row in rows:
                try:
                    stored_vec = np.frombuffer(row["embedding"], dtype=np.float32)
                    score = float(np.dot(query_vec, stored_vec))
                    scored.append((score, row))
                except Exception:
                    continue

            # Sort by similarity (highest first)
            scored.sort(key=lambda x: x[0], reverse=True)

            results = []
            for score, row in scored[:limit]:
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "source": row["source"],
                    "tags": json.loads(row["tags"]) if row["tags"] else [],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "score": score,
                    "created_at": row["created_at"],
                })

            return results
        finally:
            conn.close()

    def _recall_keyword(
        self,
        query: str,
        limit: int,
        sources: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Keyword-based fallback search."""
        conn = self._get_conn()
        try:
            sql = "SELECT id, content, source, tags, metadata, created_at FROM memories WHERE content LIKE ?"
            params: list = [f"%{query}%"]

            if sources:
                placeholders = ",".join(["?"] * len(sources))
                sql += f" AND source IN ({placeholders})"
                params.extend(sources)

            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()

            return [
                {
                    "id": row["id"],
                    "content": row["content"],
                    "source": row["source"],
                    "tags": json.loads(row["tags"]) if row["tags"] else [],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "score": 0.5,  # Keyword match gets a neutral score
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────────────────────
    # Fact Storage (Long-Term Memory)
    # ──────────────────────────────────────────────────────────────────────

    async def store_fact(
        self,
        category: str,
        content: str,
        confidence: float = 0.8,
        source: str = "extracted",
    ) -> Dict[str, Any]:
        """Store a long-term fact.

        Args:
            category: Fact category (user_preference, user_fact, learned_pattern).
            content: The fact text.
            confidence: Confidence score 0.0-1.0.
            source: Where this fact came from.

        Returns:
            Dict with 'id' and 'status'.
        """
        return self.store_fact_sync(category, content, confidence, source)

    def store_fact_sync(
        self,
        category: str,
        content: str,
        confidence: float = 0.8,
        source: str = "extracted",
    ) -> Dict[str, Any]:
        """Store a long-term fact (synchronous)."""
        fact_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO facts (id, category, content, confidence, source, created_at, last_accessed, access_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                (fact_id, category, content, confidence, source, now, now),
            )
            conn.commit()
            logger.debug("Stored fact [%s]: %s", category, content[:50])
            return {"id": fact_id, "status": "stored"}
        finally:
            conn.close()

    async def get_facts(
        self,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieve facts from long-term memory.

        Args:
            category: Filter by category.
            query: Keyword search within facts.
            limit: Max results.

        Returns:
            List of fact dicts.
        """
        return self.get_facts_sync(category, query, limit)

    def get_facts_sync(
        self,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieve facts (synchronous)."""
        conn = self._get_conn()
        try:
            conditions = []
            params: list = []

            if category:
                conditions.append("category = ?")
                params.append(category)
            if query:
                conditions.append("content LIKE ?")
                params.append(f"%{query}%")

            where = " AND ".join(conditions) if conditions else "1=1"
            sql = f"""SELECT id, category, content, confidence, source, created_at, last_accessed, access_count
                      FROM facts WHERE {where}
                      ORDER BY confidence DESC, last_accessed DESC
                      LIMIT ?"""
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()

            # Update access counts
            for row in rows:
                conn.execute(
                    "UPDATE facts SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), row["id"]),
                )
            conn.commit()

            return [
                {
                    "id": row["id"],
                    "category": row["category"],
                    "content": row["content"],
                    "confidence": row["confidence"],
                    "source": row["source"],
                    "created_at": row["created_at"],
                    "access_count": row["access_count"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────────────────────
    # Recent Memories
    # ──────────────────────────────────────────────────────────────────────

    async def get_recent(
        self,
        hours: int = 24,
        limit: int = 20,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent memories by time."""
        if self._use_rqlite:
            client = self._get_rqlite_client()
            return await client.get_recent(hours, limit, sources)

        return self.get_recent_sync(hours, limit, sources)

    def get_recent_sync(
        self,
        hours: int = 24,
        limit: int = 20,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent memories (synchronous)."""
        conn = self._get_conn()
        try:
            sql = """SELECT id, content, source, tags, metadata, created_at
                     FROM memories
                     WHERE created_at > datetime('now', ?)"""
            params: list = [f"-{hours} hours"]

            if sources:
                placeholders = ",".join(["?"] * len(sources))
                sql += f" AND source IN ({placeholders})"
                params.extend(sources)

            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()

            return [
                {
                    "id": row["id"],
                    "content": row["content"],
                    "source": row["source"],
                    "tags": json.loads(row["tags"]) if row["tags"] else [],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────────────────────
    # Identity
    # ──────────────────────────────────────────────────────────────────────

    def get_identity(self) -> str:
        """Load the canonical identity document.

        Returns:
            Full text of TIMMY_IDENTITY.md.
        """
        from brain.identity import get_canonical_identity
        return get_canonical_identity()

    def get_identity_for_prompt(self) -> str:
        """Get identity formatted for system prompt injection.

        Returns:
            Compact identity block for prompt injection.
        """
        from brain.identity import get_identity_for_prompt
        return get_identity_for_prompt()

    # ──────────────────────────────────────────────────────────────────────
    # Context Building
    # ──────────────────────────────────────────────────────────────────────

    async def get_context(self, query: str) -> str:
        """Build formatted context for system prompt.

        Combines identity + recent memories + relevant memories.

        Args:
            query: Current user query for relevance matching.

        Returns:
            Formatted context string for prompt injection.
        """
        parts = []

        # Identity (always first)
        identity = self.get_identity_for_prompt()
        if identity:
            parts.append(identity)

        # Recent activity
        recent = await self.get_recent(hours=24, limit=5)
        if recent:
            lines = ["## Recent Activity"]
            for m in recent:
                lines.append(f"- {m['content'][:100]}")
            parts.append("\n".join(lines))

        # Relevant memories
        relevant = await self.recall(query, limit=5)
        if relevant:
            lines = ["## Relevant Memories"]
            for r in relevant:
                score = r.get("score", 0)
                lines.append(f"- [{score:.2f}] {r['content'][:100]}")
            parts.append("\n".join(lines))

        return "\n\n---\n\n".join(parts)

    # ──────────────────────────────────────────────────────────────────────
    # Stats
    # ──────────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics.

        Returns:
            Dict with memory_count, fact_count, db_size_bytes, etc.
        """
        conn = self._get_conn()
        try:
            memory_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            fact_count = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            embedded_count = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL"
            ).fetchone()[0]

            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

            return {
                "memory_count": memory_count,
                "fact_count": fact_count,
                "embedded_count": embedded_count,
                "db_size_bytes": db_size,
                "backend": "rqlite" if self._use_rqlite else "local_sqlite",
                "db_path": str(self.db_path),
            }
        finally:
            conn.close()


# ──────────────────────────────────────────────────────────────────────────
# Module-level convenience
# ──────────────────────────────────────────────────────────────────────────

_default_memory: Optional[UnifiedMemory] = None


def get_memory(source: str = "timmy") -> UnifiedMemory:
    """Get the singleton UnifiedMemory instance.

    Args:
        source: Source identifier for this caller.

    Returns:
        UnifiedMemory instance.
    """
    global _default_memory
    if _default_memory is None:
        _default_memory = UnifiedMemory(source=source)
    return _default_memory


# ──────────────────────────────────────────────────────────────────────────
# Local SQLite Schema
# ──────────────────────────────────────────────────────────────────────────

_LOCAL_SCHEMA = """
-- Unified memory table (replaces vector_store, semantic_memory, etc.)
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    embedding BLOB,
    source TEXT DEFAULT 'timmy',
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

-- Long-term facts (replaces memory_layers LongTermMemory)
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    source TEXT DEFAULT 'extracted',
    created_at TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    access_count INTEGER DEFAULT 0
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_confidence ON facts(confidence);

-- Schema version
CREATE TABLE IF NOT EXISTS brain_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT
);

INSERT OR REPLACE INTO brain_schema_version (version, applied_at)
VALUES (1, datetime('now'));
"""
