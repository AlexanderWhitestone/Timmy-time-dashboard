"""Memory tools — search and write.

MCP-compliant tools for Timmy's memory system.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.registry import register_tool
from mcp.schemas.base import create_tool_schema, PARAM_STRING, PARAM_INTEGER, RETURN_STRING

logger = logging.getLogger(__name__)


# ── Memory Search ─────────────────────────────────────────────────────────────

MEMORY_SEARCH_SCHEMA = create_tool_schema(
    name="memory_search",
    description="Search Timmy's memory for past conversations, facts, and context. Use when user asks about previous discussions or when you need to recall something from memory.",
    parameters={
        "query": {
            **PARAM_STRING,
            "description": "What to search for in memory",
        },
        "top_k": {
            **PARAM_INTEGER,
            "description": "Number of results to return (1-10)",
            "default": 5,
            "minimum": 1,
            "maximum": 10,
        },
    },
    required=["query"],
    returns=RETURN_STRING,
)


def memory_search(query: str, top_k: int = 5) -> str:
    """Search Timmy's memory.
    
    Args:
        query: Search query
        top_k: Number of results
    
    Returns:
        Relevant memories from past conversations
    """
    try:
        from timmy.semantic_memory import memory_search as semantic_search
        
        results = semantic_search(query, top_k=top_k)
        
        if not results:
            return "No relevant memories found."
        
        formatted = ["Relevant memories from past conversations:", ""]
        
        for i, (content, score) in enumerate(results, 1):
            relevance = "🔥" if score > 0.8 else "⭐" if score > 0.5 else "📄"
            formatted.append(f"{relevance} [{i}] (score: {score:.2f})")
            formatted.append(f"    {content[:300]}...")
            formatted.append("")
        
        return "\n".join(formatted)
        
    except Exception as exc:
        logger.error("Memory search failed: %s", exc)
        return f"Memory search error: {exc}"


# ── Memory Write ──────────────────────────────────────────────────────────────

MEMORY_WRITE_SCHEMA = create_tool_schema(
    name="memory_write",
    description="Write a memory entry to persistent storage. Use when the user teaches you something, corrects you, or asks you to remember something important. This persists across sessions.",
    parameters={
        "content": {
            **PARAM_STRING,
            "description": "The content to remember — be specific and concise",
        },
        "category": {
            **PARAM_STRING,
            "description": "Category: lesson (something you learned), preference (user preference), fact (important info), todo (action item)",
            "default": "fact",
        },
        "tags": {
            **PARAM_STRING,
            "description": "Comma-separated tags for this memory (e.g., 'git,tools,correction')",
            "default": "",
        },
    },
    required=["content"],
    returns=RETURN_STRING,
)


def memory_write(content: str, category: str = "fact", tags: str = "") -> str:
    """Write a memory entry to persistent storage.
    
    This writes to MEMORY.md (hot memory) and optionally to the vault
    for long-term semantic search.
    
    Args:
        content: The content to remember
        category: Type of memory (lesson, preference, fact, todo)
        tags: Comma-separated tags
    
    Returns:
        Confirmation that memory was saved
    """
    try:
        from config import settings
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        
        # Format the memory entry
        entry_lines = [f"### {timestamp} — {category.upper()}"]
        if tags:
            entry_lines.append(f"**Tags:** {tags}")
        entry_lines.append("")
        entry_lines.append(content)
        entry_lines.append("")
        entry_lines.append("---")
        entry_lines.append("")
        
        entry = "\n".join(entry_lines)
        
        # Write to MEMORY.md (hot memory)
        memory_path = Path(settings.repo_root) / "MEMORY.md"
        if memory_path.exists():
            # Append after the first header
            existing = memory_path.read_text()
            lines = existing.split("\n")
            
            # Find where to insert (after header/frontmatter)
            insert_idx = 0
            for i, line in enumerate(lines):
                if i > 0 and line.startswith("#"):
                    insert_idx = i
                    break
                if i > 10:  # Safety limit
                    insert_idx = i
                    break
            
            lines.insert(insert_idx, entry)
            memory_path.write_text("\n".join(lines))
        else:
            # Create new MEMORY.md
            header = f"""# Timmy Hot Memory

> Working RAM — always loaded, ~300 lines max, pruned monthly
> Last updated: {timestamp[:10]}

---

"""
            memory_path.write_text(header + entry)
        
        # Note: Semantic memory (vector search) integration can be added here
        # For now, MEMORY.md serves as the hot memory that is always loaded
        
        logger.info("Memory written [%s]: %s...", category, content[:60])
        return f"✓ Memory saved ({category}): {content[:100]}{'...' if len(content) > 100 else ''}"
        
    except Exception as exc:
        logger.error("Memory write failed: %s", exc)
        return f"Failed to save memory: {exc}"


def write_session_summary(messages: list[dict]) -> None:
    """Write a session summary at session end.
    
    This is called automatically when the session ends (page refresh,
    clear chat, or timeout).
    
    Args:
        messages: List of message dicts with 'role' and 'content'
    """
    try:
        # Extract key information from the conversation
        lessons = []
        requests = []
        bugs = []
        
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "").lower()
            
            # Look for corrections
            if any(word in content for word in ["wrong", "incorrect", "no,", "not right", "fabricat", "hallucinat"]):
                lessons.append(f"Correction: {msg['content'][:100]}")
            
            # Look for feature requests
            if any(word in content for word in ["add", "implement", "create", "build", "feature"]):
                requests.append(msg['content'][:100])
            
            # Look for bug reports
            if any(word in content for word in ["bug", "broken", "error", "fail", "issue"]):
                bugs.append(msg['content'][:100])
        
        if not (lessons or requests or bugs):
            return  # Nothing notable to save
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        
        lines = [f"## Session Summary — {timestamp}", ""]
        
        if lessons:
            lines.append("### Key Lessons")
            for lesson in lessons[:5]:
                lines.append(f"- {lesson}")
            lines.append("")
        
        if requests:
            lines.append("### User Requests")
            for req in requests[:5]:
                lines.append(f"- {req}")
            lines.append("")
        
        if bugs:
            lines.append("### Bugs Confirmed")
            for bug in bugs[:5]:
                lines.append(f"- {bug}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        
        summary = "\n".join(lines)
        
        # Append to MEMORY.md
        from config import settings
        memory_path = Path(settings.repo_root) / "MEMORY.md"
        if memory_path.exists():
            existing = memory_path.read_text()
            lines = existing.split("\n")
            
            # Insert after frontmatter
            insert_idx = 0
            for i, line in enumerate(lines):
                if i > 0 and line.startswith("## "):
                    insert_idx = i
                    break
            
            lines.insert(insert_idx, summary)
            memory_path.write_text("\n".join(lines))
            logger.info("Session summary written to MEMORY.md")
            
    except Exception as exc:
        logger.error("Failed to write session summary: %s", exc)


# ── Register with MCP ─────────────────────────────────────────────────────────

register_tool(name="memory_search", schema=MEMORY_SEARCH_SCHEMA, category="memory")(memory_search)
register_tool(name="memory_write", schema=MEMORY_WRITE_SCHEMA, category="memory")(memory_write)
