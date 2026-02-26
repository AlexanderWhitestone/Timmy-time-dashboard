"""Memory search tool.

MCP-compliant tool for searching Timmy's memory.
"""

import logging
from typing import Any

from mcp.registry import register_tool
from mcp.schemas.base import create_tool_schema, PARAM_STRING, PARAM_INTEGER, RETURN_STRING

logger = logging.getLogger(__name__)


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


# Register with MCP
register_tool(name="memory_search", schema=MEMORY_SEARCH_SCHEMA, category="memory")(memory_search)
