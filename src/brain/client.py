"""Brain client — interface to distributed rqlite memory.

All devices connect to the local rqlite node, which replicates to peers.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_RQLITE_URL = "http://localhost:4001"


class BrainClient:
    """Client for distributed brain (rqlite).
    
    Connects to local rqlite instance, which handles replication.
    All writes go to leader, reads can come from local node.
    """
    
    def __init__(self, rqlite_url: Optional[str] = None, node_id: Optional[str] = None):
        self.rqlite_url = rqlite_url or os.environ.get("RQLITE_URL", DEFAULT_RQLITE_URL)
        self.node_id = node_id or f"{socket.gethostname()}-{os.getpid()}"
        self.source = self._detect_source()
        self._client = httpx.AsyncClient(timeout=30)
        
    def _detect_source(self) -> str:
        """Detect what component is using the brain."""
        # Could be 'timmy', 'zeroclaw', 'worker', etc.
        # For now, infer from context or env
        return os.environ.get("BRAIN_SOURCE", "default")
    
    # ──────────────────────────────────────────────────────────────────────────
    # Memory Operations
    # ──────────────────────────────────────────────────────────────────────────
    
    async def remember(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Store a memory with embedding.
        
        Args:
            content: Text content to remember
            tags: Optional list of tags (e.g., ['shell', 'result'])
            source: Source identifier (defaults to self.source)
            metadata: Additional JSON-serializable metadata
            
        Returns:
            Dict with 'id' and 'status'
        """
        from brain.embeddings import get_embedder
        
        embedder = get_embedder()
        embedding_bytes = embedder.encode_single(content)
        
        query = """
            INSERT INTO memories (content, embedding, source, tags, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = [
            content,
            embedding_bytes,
            source or self.source,
            json.dumps(tags or []),
            json.dumps(metadata or {}),
            datetime.utcnow().isoformat()
        ]
        
        try:
            resp = await self._client.post(
                f"{self.rqlite_url}/db/execute",
                json=[query, params]
            )
            resp.raise_for_status()
            result = resp.json()
            
            # Extract inserted ID
            last_id = None
            if "results" in result and result["results"]:
                last_id = result["results"][0].get("last_insert_id")
            
            logger.debug(f"Stored memory {last_id}: {content[:50]}...")
            return {"id": last_id, "status": "stored"}
            
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            raise
    
    async def recall(
        self,
        query: str,
        limit: int = 5,
        sources: Optional[List[str]] = None
    ) -> List[str]:
        """Semantic search for memories.
        
        Args:
            query: Search query text
            limit: Max results to return
            sources: Filter by source(s) (e.g., ['timmy', 'user'])
            
        Returns:
            List of memory content strings
        """
        from brain.embeddings import get_embedder
        
        embedder = get_embedder()
        query_emb = embedder.encode_single(query)
        
        # rqlite with sqlite-vec extension for vector search
        sql = "SELECT content, source, metadata, distance FROM memories WHERE embedding MATCH ?"
        params = [query_emb]
        
        if sources:
            placeholders = ",".join(["?"] * len(sources))
            sql += f" AND source IN ({placeholders})"
            params.extend(sources)
        
        sql += " ORDER BY distance LIMIT ?"
        params.append(limit)
        
        try:
            resp = await self._client.post(
                f"{self.rqlite_url}/db/query",
                json=[sql, params]
            )
            resp.raise_for_status()
            result = resp.json()
            
            results = []
            if "results" in result and result["results"]:
                for row in result["results"][0].get("rows", []):
                    results.append({
                        "content": row[0],
                        "source": row[1],
                        "metadata": json.loads(row[2]) if row[2] else {},
                        "distance": row[3]
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            # Graceful fallback - return empty list
            return []
    
    async def get_recent(
        self,
        hours: int = 24,
        limit: int = 20,
        sources: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get recent memories by time.
        
        Args:
            hours: Look back this many hours
            limit: Max results
            sources: Optional source filter
            
        Returns:
            List of memory dicts
        """
        sql = """
            SELECT id, content, source, tags, metadata, created_at
            FROM memories
            WHERE created_at > datetime('now', ?)
        """
        params = [f"-{hours} hours"]
        
        if sources:
            placeholders = ",".join(["?"] * len(sources))
            sql += f" AND source IN ({placeholders})"
            params.extend(sources)
        
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        try:
            resp = await self._client.post(
                f"{self.rqlite_url}/db/query",
                json=[sql, params]
            )
            resp.raise_for_status()
            result = resp.json()
            
            memories = []
            if "results" in result and result["results"]:
                for row in result["results"][0].get("rows", []):
                    memories.append({
                        "id": row[0],
                        "content": row[1],
                        "source": row[2],
                        "tags": json.loads(row[3]) if row[3] else [],
                        "metadata": json.loads(row[4]) if row[4] else {},
                        "created_at": row[5]
                    })
            
            return memories
            
        except Exception as e:
            logger.error(f"Failed to get recent memories: {e}")
            return []
    
    async def get_context(self, query: str) -> str:
        """Get formatted context for system prompt.
        
        Combines recent memories + relevant memories.
        
        Args:
            query: Current user query to find relevant context
            
        Returns:
            Formatted context string for prompt injection
        """
        recent = await self.get_recent(hours=24, limit=10)
        relevant = await self.recall(query, limit=5)
        
        lines = ["Recent activity:"]
        for m in recent[:5]:
            lines.append(f"- {m['content'][:100]}")
        
        lines.append("\nRelevant memories:")
        for r in relevant[:5]:
            lines.append(f"- {r['content'][:100]}")
        
        return "\n".join(lines)
    
    # ──────────────────────────────────────────────────────────────────────────
    # Task Queue Operations
    # ──────────────────────────────────────────────────────────────────────────
    
    async def submit_task(
        self,
        content: str,
        task_type: str = "general",
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Submit a task to the distributed queue.
        
        Args:
            content: Task description/prompt
            task_type: Type of task (shell, creative, code, research, general)
            priority: Higher = processed first
            metadata: Additional task data
            
        Returns:
            Dict with task 'id'
        """
        query = """
            INSERT INTO tasks (content, task_type, priority, status, metadata, created_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
        """
        params = [
            content,
            task_type,
            priority,
            json.dumps(metadata or {}),
            datetime.utcnow().isoformat()
        ]
        
        try:
            resp = await self._client.post(
                f"{self.rqlite_url}/db/execute",
                json=[query, params]
            )
            resp.raise_for_status()
            result = resp.json()
            
            last_id = None
            if "results" in result and result["results"]:
                last_id = result["results"][0].get("last_insert_id")
            
            logger.info(f"Submitted task {last_id}: {content[:50]}...")
            return {"id": last_id, "status": "queued"}
            
        except Exception as e:
            logger.error(f"Failed to submit task: {e}")
            raise
    
    async def claim_task(
        self,
        capabilities: List[str],
        node_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Atomically claim next available task.
        
        Uses UPDATE ... RETURNING pattern for atomic claim.
        
        Args:
            capabilities: List of capabilities this node has
            node_id: Identifier for claiming node
            
        Returns:
            Task dict or None if no tasks available
        """
        claimer = node_id or self.node_id
        
        # Try to claim a matching task atomically
        # This works because rqlite uses Raft consensus - only one node wins
        placeholders = ",".join(["?"] * len(capabilities))
        
        query = f"""
            UPDATE tasks 
            SET status = 'claimed', 
                claimed_by = ?,
                claimed_at = ?
            WHERE id = (
                SELECT id FROM tasks 
                WHERE status = 'pending'
                AND (task_type IN ({placeholders}) OR task_type = 'general')
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            )
            AND status = 'pending'
            RETURNING id, content, task_type, priority, metadata
        """
        params = [claimer, datetime.utcnow().isoformat()] + capabilities
        
        try:
            resp = await self._client.post(
                f"{self.rqlite_url}/db/execute",
                json=[query, params]
            )
            resp.raise_for_status()
            result = resp.json()
            
            if "results" in result and result["results"]:
                rows = result["results"][0].get("rows", [])
                if rows:
                    row = rows[0]
                    return {
                        "id": row[0],
                        "content": row[1],
                        "type": row[2],
                        "priority": row[3],
                        "metadata": json.loads(row[4]) if row[4] else {}
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to claim task: {e}")
            return None
    
    async def complete_task(
        self,
        task_id: int,
        success: bool,
        result: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """Mark task as completed or failed.
        
        Args:
            task_id: Task ID
            success: True if task succeeded
            result: Task result/output
            error: Error message if failed
        """
        status = "done" if success else "failed"
        
        query = """
            UPDATE tasks 
            SET status = ?, 
                result = ?,
                error = ?,
                completed_at = ?
            WHERE id = ?
        """
        params = [status, result, error, datetime.utcnow().isoformat(), task_id]
        
        try:
            await self._client.post(
                f"{self.rqlite_url}/db/execute",
                json=[query, params]
            )
            logger.debug(f"Task {task_id} marked {status}")
            
        except Exception as e:
            logger.error(f"Failed to complete task {task_id}: {e}")
    
    async def get_pending_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get list of pending tasks (for dashboard/monitoring).
        
        Args:
            limit: Max tasks to return
            
        Returns:
            List of pending task dicts
        """
        sql = """
            SELECT id, content, task_type, priority, metadata, created_at
            FROM tasks
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
        """
        
        try:
            resp = await self._client.post(
                f"{self.rqlite_url}/db/query",
                json=[sql, [limit]]
            )
            resp.raise_for_status()
            result = resp.json()
            
            tasks = []
            if "results" in result and result["results"]:
                for row in result["results"][0].get("rows", []):
                    tasks.append({
                        "id": row[0],
                        "content": row[1],
                        "type": row[2],
                        "priority": row[3],
                        "metadata": json.loads(row[4]) if row[4] else {},
                        "created_at": row[5]
                    })
            
            return tasks
            
        except Exception as e:
            logger.error(f"Failed to get pending tasks: {e}")
            return []
    
    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()
