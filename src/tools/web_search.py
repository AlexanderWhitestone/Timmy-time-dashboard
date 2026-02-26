"""Web search tool using DuckDuckGo.

MCP-compliant tool for searching the web.
"""

import logging
from typing import Any

from mcp.registry import register_tool
from mcp.schemas.base import create_tool_schema, PARAM_STRING, PARAM_INTEGER, RETURN_STRING

logger = logging.getLogger(__name__)


WEB_SEARCH_SCHEMA = create_tool_schema(
    name="web_search",
    description="Search the web using DuckDuckGo. Use for current events, news, real-time data, and information not in your training data.",
    parameters={
        "query": {
            **PARAM_STRING,
            "description": "Search query string",
        },
        "max_results": {
            **PARAM_INTEGER,
            "description": "Maximum number of results (1-10)",
            "default": 5,
            "minimum": 1,
            "maximum": 10,
        },
    },
    required=["query"],
    returns=RETURN_STRING,
)


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo.
    
    Args:
        query: Search query
        max_results: Maximum results to return
    
    Returns:
        Formatted search results
    """
    try:
        from duckduckgo_search import DDGS
        
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        
        if not results:
            return "No results found."
        
        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            body = r.get("body", "No description")
            href = r.get("href", "")
            formatted.append(f"{i}. {title}\n   {body[:150]}...\n   {href}")
        
        return "\n\n".join(formatted)
        
    except Exception as exc:
        logger.error("Web search failed: %s", exc)
        return f"Search error: {exc}"


# Register with MCP
register_tool(
    name="web_search",
    schema=WEB_SEARCH_SCHEMA,
    category="research",
)(web_search)
