"""Multi-layer memory system for Timmy.

.. deprecated::
    This module is deprecated and unused.  The active memory system lives in
    ``timmy.memory_system`` (three-tier: Hot/Vault/Handoff) and
    ``timmy.conversation`` (working conversation context).

    This file is retained for reference only.  Do not import from it.

Implements four distinct memory layers:

1. WORKING MEMORY (Context Window)
   - Last 20 messages in current conversation
   - Fast access, ephemeral
   - Used for: Immediate context, pronoun resolution, topic tracking

2. SHORT-TERM MEMORY (Recent History)
   - SQLite storage via Agno (last 100 conversations)
   - Persists across restarts
   - Used for: Recent context, conversation continuity

3. LONG-TERM MEMORY (Facts & Preferences)
   - Key facts about user, preferences, important events
   - Explicitly extracted and stored
   - Used for: Personalization, user model

4. SEMANTIC MEMORY (Vector Search)
   - Embeddings of past conversations
   - Similarity-based retrieval
   - Used for: "Have we talked about this before?"

All layers work together to provide contextual, personalized responses.
"""

import warnings as _warnings

_warnings.warn(
    "timmy.memory_layers is deprecated. Use timmy.memory_system and "
    "timmy.conversation instead.",
    DeprecationWarning,
    stacklevel=2,
)

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Paths for memory storage
MEMORY_DIR = Path("data/memory")
LTM_PATH = MEMORY_DIR / "long_term_memory.db"
SEMANTIC_PATH = MEMORY_DIR / "semantic_memory.db"


# =============================================================================
# LAYER 1: WORKING MEMORY (Active Conversation Context)
# =============================================================================

@dataclass
class WorkingMemoryEntry:
    """A single entry in working memory."""
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)


class WorkingMemory:
    """Fast, ephemeral context window (last N messages).
    
    Used for:
    - Immediate conversational context
    - Pronoun resolution ("Tell me more about it")
    - Topic continuity
    - Tool call tracking
    """
    
    def __init__(self, max_entries: int = 20) -> None:
        self.max_entries = max_entries
        self.entries: list[WorkingMemoryEntry] = []
        self.current_topic: Optional[str] = None
        self.pending_tool_calls: list[dict] = []
    
    def add(self, role: str, content: str, metadata: Optional[dict] = None) -> None:
        """Add an entry to working memory."""
        entry = WorkingMemoryEntry(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.entries.append(entry)
        
        # Trim to max size
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        
        logger.debug("WorkingMemory: Added %s entry (total: %d)", role, len(self.entries))
    
    def get_context(self, n: Optional[int] = None) -> list[WorkingMemoryEntry]:
        """Get last n entries (or all if n not specified)."""
        if n is None:
            return self.entries.copy()
        return self.entries[-n:]
    
    def get_formatted_context(self, n: int = 10) -> str:
        """Get formatted context for prompt injection."""
        entries = self.get_context(n)
        lines = []
        for entry in entries:
            role_label = "User" if entry.role == "user" else "Timmy" if entry.role == "assistant" else "System"
            lines.append(f"{role_label}: {entry.content}")
        return "\n".join(lines)
    
    def set_topic(self, topic: str) -> None:
        """Set the current conversation topic."""
        self.current_topic = topic
        logger.debug("WorkingMemory: Topic set to '%s'", topic)
    
    def clear(self) -> None:
        """Clear working memory (new conversation)."""
        self.entries.clear()
        self.current_topic = None
        self.pending_tool_calls.clear()
        logger.debug("WorkingMemory: Cleared")
    
    def track_tool_call(self, tool_name: str, parameters: dict) -> None:
        """Track a pending tool call."""
        self.pending_tool_calls.append({
            "tool": tool_name,
            "params": parameters,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    @property
    def turn_count(self) -> int:
        """Count user-assistant exchanges."""
        return sum(1 for e in self.entries if e.role in ("user", "assistant"))


# =============================================================================
# LAYER 3: LONG-TERM MEMORY (Facts & Preferences)
# =============================================================================

@dataclass
class LongTermMemoryFact:
    """A single fact in long-term memory."""
    id: str
    category: str  # "user_preference", "user_fact", "important_event", "learned_pattern"
    content: str
    confidence: float  # 0.0 - 1.0
    source: str  # conversation_id or "extracted"
    created_at: str
    last_accessed: str
    access_count: int = 0


class LongTermMemory:
    """Persistent storage for important facts and preferences.
    
    Used for:
    - User's name, preferences, interests
    - Important facts learned about the user
    - Successful patterns and strategies
    """
    
    def __init__(self) -> None:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize SQLite database."""
        conn = sqlite3.connect(str(LTM_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                source TEXT,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                access_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON facts(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content ON facts(content)")
        conn.commit()
        conn.close()
    
    def store(
        self,
        category: str,
        content: str,
        confidence: float = 0.8,
        source: str = "extracted"
    ) -> str:
        """Store a fact in long-term memory."""
        fact_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        conn = sqlite3.connect(str(LTM_PATH))
        try:
            conn.execute(
                """INSERT INTO facts (id, category, content, confidence, source, created_at, last_accessed)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (fact_id, category, content, confidence, source, now, now)
            )
            conn.commit()
            logger.info("LTM: Stored %s fact: %s", category, content[:50])
            return fact_id
        finally:
            conn.close()
    
    def retrieve(
        self,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 10
    ) -> list[LongTermMemoryFact]:
        """Retrieve facts from long-term memory."""
        conn = sqlite3.connect(str(LTM_PATH))
        conn.row_factory = sqlite3.Row
        
        try:
            if category and query:
                rows = conn.execute(
                    """SELECT * FROM facts 
                       WHERE category = ? AND content LIKE ?
                       ORDER BY confidence DESC, access_count DESC
                       LIMIT ?""",
                    (category, f"%{query}%", limit)
                ).fetchall()
            elif category:
                rows = conn.execute(
                    """SELECT * FROM facts 
                       WHERE category = ?
                       ORDER BY confidence DESC, last_accessed DESC
                       LIMIT ?""",
                    (category, limit)
                ).fetchall()
            elif query:
                rows = conn.execute(
                    """SELECT * FROM facts 
                       WHERE content LIKE ?
                       ORDER BY confidence DESC, access_count DESC
                       LIMIT ?""",
                    (f"%{query}%", limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM facts 
                       ORDER BY last_accessed DESC
                       LIMIT ?""",
                    (limit,)
                ).fetchall()
            
            # Update access count
            fact_ids = [row["id"] for row in rows]
            for fid in fact_ids:
                conn.execute(
                    "UPDATE facts SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), fid)
                )
            conn.commit()
            
            return [
                LongTermMemoryFact(
                    id=row["id"],
                    category=row["category"],
                    content=row["content"],
                    confidence=row["confidence"],
                    source=row["source"],
                    created_at=row["created_at"],
                    last_accessed=row["last_accessed"],
                    access_count=row["access_count"]
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def get_user_profile(self) -> dict:
        """Get consolidated user profile from stored facts."""
        preferences = self.retrieve(category="user_preference")
        facts = self.retrieve(category="user_fact")
        
        profile = {
            "name": None,
            "preferences": {},
            "interests": [],
            "facts": []
        }
        
        for pref in preferences:
            if "name is" in pref.content.lower():
                profile["name"] = pref.content.split("is")[-1].strip().rstrip(".")
            else:
                profile["preferences"][pref.id] = pref.content
        
        for fact in facts:
            profile["facts"].append(fact.content)
        
        return profile
    
    def extract_and_store(self, user_message: str, assistant_response: str) -> list[str]:
        """Extract potential facts from conversation and store them.
        
        This is a simple rule-based extractor. In production, this could
        use an LLM to extract facts.
        """
        stored_ids = []
        message_lower = user_message.lower()
        
        # Extract name
        name_patterns = ["my name is", "i'm ", "i am ", "call me " ]
        for pattern in name_patterns:
            if pattern in message_lower:
                idx = message_lower.find(pattern) + len(pattern)
                name = user_message[idx:].strip().split()[0].strip(".,!?;:").capitalize()
                if name and len(name) > 1:
                    sid = self.store(
                        category="user_fact",
                        content=f"User's name is {name}",
                        confidence=0.9,
                        source="extracted_from_conversation"
                    )
                    stored_ids.append(sid)
                break
        
        # Extract preferences ("I like", "I prefer", "I don't like")
        preference_patterns = [
            ("i like", "user_preference", "User likes"),
            ("i love", "user_preference", "User loves"),
            ("i prefer", "user_preference", "User prefers"),
            ("i don't like", "user_preference", "User dislikes"),
            ("i hate", "user_preference", "User dislikes"),
        ]
        
        for pattern, category, prefix in preference_patterns:
            if pattern in message_lower:
                idx = message_lower.find(pattern) + len(pattern)
                preference = user_message[idx:].strip().split(".")[0].strip()
                if preference and len(preference) > 3:
                    sid = self.store(
                        category=category,
                        content=f"{prefix} {preference}",
                        confidence=0.7,
                        source="extracted_from_conversation"
                    )
                    stored_ids.append(sid)
        
        return stored_ids


# =============================================================================
# MEMORY MANAGER (Integrates all layers)
# =============================================================================

class MemoryManager:
    """Central manager for all memory layers.
    
    Coordinates between:
    - Working Memory (immediate context)
    - Short-term Memory (Agno SQLite)
    - Long-term Memory (facts/preferences)
    - (Future: Semantic Memory with embeddings)
    """
    
    def __init__(self) -> None:
        self.working = WorkingMemory(max_entries=20)
        self.long_term = LongTermMemory()
        self._session_id: Optional[str] = None
    
    def start_session(self, session_id: Optional[str] = None) -> str:
        """Start a new conversation session."""
        self._session_id = session_id or str(uuid.uuid4())
        self.working.clear()
        
        # Load relevant LTM into context
        profile = self.long_term.get_user_profile()
        if profile["name"]:
            logger.info("MemoryManager: Recognizing user '%s'", profile["name"])
        
        return self._session_id
    
    def add_exchange(
        self,
        user_message: str,
        assistant_response: str,
        tool_calls: Optional[list] = None
    ) -> None:
        """Record a complete exchange across all memory layers."""
        # Working memory
        self.working.add("user", user_message)
        self.working.add("assistant", assistant_response, metadata={"tools": tool_calls})
        
        # Extract and store facts to LTM
        try:
            self.long_term.extract_and_store(user_message, assistant_response)
        except Exception as exc:
            logger.warning("Failed to extract facts: %s", exc)
    
    def get_context_for_prompt(self) -> str:
        """Generate context string for injection into prompts."""
        parts = []
        
        # User profile from LTM
        profile = self.long_term.get_user_profile()
        if profile["name"]:
            parts.append(f"User's name: {profile['name']}")
        
        if profile["preferences"]:
            prefs = list(profile["preferences"].values())[:3]  # Top 3 preferences
            parts.append("User preferences: " + "; ".join(prefs))
        
        # Recent working memory
        working_context = self.working.get_formatted_context(n=6)
        if working_context:
            parts.append("Recent conversation:\n" + working_context)
        
        return "\n\n".join(parts) if parts else ""
    
    def get_relevant_memories(self, query: str) -> list[str]:
        """Get memories relevant to current query."""
        # Get from LTM
        facts = self.long_term.retrieve(query=query, limit=5)
        return [f.content for f in facts]


# Singleton removed — this module is deprecated.
# Use timmy.memory_system.memory_system or timmy.conversation.conversation_manager.
