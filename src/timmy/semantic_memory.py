"""Tier 3: Semantic Memory — Vector search over vault files.

Uses lightweight local embeddings (no cloud) for similarity search
over all vault content. This is the "escape valve" when hot memory
doesn't have the answer.

Architecture:
- Indexes all markdown files in memory/ nightly or on-demand
- Uses sentence-transformers (local, no API calls)
- Stores vectors in SQLite (no external vector DB needed)
- memory_search() retrieves relevant context by similarity
"""

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
VAULT_PATH = PROJECT_ROOT / "memory"
SEMANTIC_DB_PATH = PROJECT_ROOT / "data" / "semantic_memory.db"

# Embedding model - small, fast, local
# Using 'all-MiniLM-L6-v2' (~80MB) or fallback to simple keyword matching
EMBEDDING_MODEL = None
EMBEDDING_DIM = 384  # MiniLM dimension


def _get_embedding_model():
    """Lazy-load embedding model."""
    global EMBEDDING_MODEL
    if EMBEDDING_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("SemanticMemory: Loaded embedding model")
        except ImportError:
            logger.warning("SemanticMemory: sentence-transformers not installed, using fallback")
            EMBEDDING_MODEL = False  # Use fallback
    return EMBEDDING_MODEL


def _simple_hash_embedding(text: str) -> list[float]:
    """Fallback: Simple hash-based embedding when transformers unavailable."""
    # Create a deterministic pseudo-embedding from word hashes
    words = text.lower().split()
    vec = [0.0] * 128
    for i, word in enumerate(words[:50]):  # First 50 words
        h = hashlib.md5(word.encode()).hexdigest()
        for j in range(8):
            idx = (i * 8 + j) % 128
            vec[idx] += int(h[j*2:j*2+2], 16) / 255.0
    # Normalize
    import math
    mag = math.sqrt(sum(x*x for x in vec)) or 1.0
    return [x/mag for x in vec]


def embed_text(text: str) -> list[float]:
    """Generate embedding for text."""
    model = _get_embedding_model()
    if model and model is not False:
        embedding = model.encode(text)
        return embedding.tolist()
    else:
        return _simple_hash_embedding(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    import math
    dot = sum(x*y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


@dataclass
class MemoryChunk:
    """A searchable chunk of memory."""
    id: str
    source: str  # filepath
    content: str
    embedding: list[float]
    created_at: str


class SemanticMemory:
    """Vector-based semantic search over vault content."""
    
    def __init__(self) -> None:
        self.db_path = SEMANTIC_DB_PATH
        self.vault_path = VAULT_PATH
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize SQLite with vector storage."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding TEXT NOT NULL,  -- JSON array
                created_at TEXT NOT NULL,
                source_hash TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON chunks(source)")
        conn.commit()
        conn.close()
    
    def index_file(self, filepath: Path) -> int:
        """Index a single file into semantic memory."""
        if not filepath.exists():
            return 0
        
        content = filepath.read_text()
        file_hash = hashlib.md5(content.encode()).hexdigest()
        
        # Check if already indexed with same hash
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT source_hash FROM chunks WHERE source = ? LIMIT 1",
            (str(filepath),)
        )
        existing = cursor.fetchone()
        if existing and existing[0] == file_hash:
            conn.close()
            return 0  # Already indexed
        
        # Delete old chunks for this file
        conn.execute("DELETE FROM chunks WHERE source = ?", (str(filepath),))
        
        # Split into chunks (paragraphs)
        chunks = self._split_into_chunks(content)
        
        # Index each chunk
        now = datetime.now(timezone.utc).isoformat()
        for i, chunk_text in enumerate(chunks):
            if len(chunk_text.strip()) < 20:  # Skip tiny chunks
                continue
            
            chunk_id = f"{filepath.stem}_{i}"
            embedding = embed_text(chunk_text)
            
            conn.execute(
                """INSERT INTO chunks (id, source, content, embedding, created_at, source_hash)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chunk_id, str(filepath), chunk_text, json.dumps(embedding), now, file_hash)
            )
        
        conn.commit()
        conn.close()
        
        logger.info("SemanticMemory: Indexed %s (%d chunks)", filepath.name, len(chunks))
        return len(chunks)
    
    def _split_into_chunks(self, text: str, max_chunk_size: int = 500) -> list[str]:
        """Split text into semantic chunks."""
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        chunks = []
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # If paragraph is small enough, keep as one chunk
            if len(para) <= max_chunk_size:
                chunks.append(para)
            else:
                # Split long paragraphs by sentences
                sentences = para.replace('. ', '.\n').split('\n')
                current_chunk = ""
                
                for sent in sentences:
                    if len(current_chunk) + len(sent) < max_chunk_size:
                        current_chunk += " " + sent if current_chunk else sent
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sent
                
                if current_chunk:
                    chunks.append(current_chunk.strip())
        
        return chunks
    
    def index_vault(self) -> int:
        """Index entire vault directory."""
        total_chunks = 0
        
        for md_file in self.vault_path.rglob("*.md"):
            # Skip handoff file (handled separately)
            if "last-session-handoff" in md_file.name:
                continue
            total_chunks += self.index_file(md_file)
        
        logger.info("SemanticMemory: Indexed vault (%d total chunks)", total_chunks)
        return total_chunks
    
    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Search for relevant memory chunks."""
        query_embedding = embed_text(query)
        
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        
        # Get all chunks (in production, use vector index)
        rows = conn.execute(
            "SELECT source, content, embedding FROM chunks"
        ).fetchall()
        
        conn.close()
        
        # Calculate similarities
        scored = []
        for row in rows:
            embedding = json.loads(row["embedding"])
            score = cosine_similarity(query_embedding, embedding)
            scored.append((row["source"], row["content"], score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[2], reverse=True)
        
        # Return top_k
        return [(content, score) for _, content, score in scored[:top_k]]
    
    def get_relevant_context(self, query: str, max_chars: int = 2000) -> str:
        """Get formatted context string for a query."""
        results = self.search(query, top_k=3)
        
        if not results:
            return ""
        
        parts = []
        total_chars = 0
        
        for content, score in results:
            if score < 0.3:  # Similarity threshold
                continue
            
            chunk = f"[Relevant memory - score {score:.2f}]: {content[:400]}..."
            if total_chars + len(chunk) > max_chars:
                break
            
            parts.append(chunk)
            total_chars += len(chunk)
        
        return "\n\n".join(parts) if parts else ""
    
    def stats(self) -> dict:
        """Get indexing statistics."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT COUNT(*), COUNT(DISTINCT source) FROM chunks")
        total_chunks, total_files = cursor.fetchone()
        conn.close()
        
        return {
            "total_chunks": total_chunks,
            "total_files": total_files,
            "embedding_dim": EMBEDDING_DIM if _get_embedding_model() else 128,
        }


class MemorySearcher:
    """High-level interface for memory search."""
    
    def __init__(self) -> None:
        self.semantic = SemanticMemory()
    
    def search(self, query: str, tiers: list[str] = None) -> dict:
        """Search across memory tiers.
        
        Args:
            query: Search query
            tiers: List of tiers to search ["hot", "vault", "semantic"]
        
        Returns:
            Dict with results from each tier
        """
        tiers = tiers or ["semantic"]  # Default to semantic only
        results = {}
        
        if "semantic" in tiers:
            semantic_results = self.semantic.search(query, top_k=5)
            results["semantic"] = [
                {"content": content, "score": score}
                for content, score in semantic_results
            ]
        
        return results
    
    def get_context_for_query(self, query: str) -> str:
        """Get comprehensive context for a user query."""
        # Get semantic context
        semantic_context = self.semantic.get_relevant_context(query)
        
        if semantic_context:
            return f"## Relevant Past Context\n\n{semantic_context}"
        
        return ""


# Module-level singleton
semantic_memory = SemanticMemory()
memory_searcher = MemorySearcher()


def memory_search(query: str, top_k: int = 5) -> list[tuple[str, float]]:
    """Simple interface for memory search."""
    return semantic_memory.search(query, top_k)
