"""Toolsets — sub-agent capabilities exposed as tool descriptions.

Instead of routing through multiple agents (Helm → Seer/Forge/Quill/Echo),
the main Timmy agent directly uses these toolsets. Each toolset describes
a capability and the tools it uses.

This simplifies the architecture from:
    User → Timmy → Helm → {Seer, Forge, Quill, Echo}
To:
    User → Timmy (with toolsets)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_toolsets() -> dict[str, dict[str, Any]]:
    """Get all available toolsets.

    Returns:
        Dict mapping capability name to toolset metadata.
    """
    return {
        "research": {
            "description": "Research and information gathering — web search, fact-checking, source evaluation.",
            "tools": ["web_search", "read_file", "memory_search"],
        },
        "code": {
            "description": "Code generation and tool building — Python, scripts, file operations, debugging.",
            "tools": ["python", "write_file", "read_file", "list_directory"],
        },
        "writing": {
            "description": "Writing and documentation — content creation, editing, summarization.",
            "tools": ["write_file", "read_file", "memory_search"],
        },
        "memory": {
            "description": "Memory and context retrieval — past conversations, user preferences, session history.",
            "tools": ["memory_search", "read_file", "write_file"],
        },
    }


def classify_request(request: str) -> str:
    """Classify a user request into a toolset category.

    Simple keyword-based classification that replaces the Helm
    routing agent. This is faster and more predictable.

    Args:
        request: The user's request text.

    Returns:
        One of: 'direct', 'memory', 'research', 'code', 'writing'.
    """
    request_lower = request.lower()

    # Direct response patterns (no toolset needed)
    direct_patterns = [
        "your name", "who are you", "what are you",
        "hello", "hi ", "how are you",
        "help", "what can you do",
    ]
    for pattern in direct_patterns:
        if pattern in request_lower:
            return "direct"

    # Memory patterns
    memory_patterns = [
        "we talked about", "we discussed", "remember",
        "what did i say", "what did we decide",
        "remind me", "have we", "yesterday",
    ]
    for pattern in memory_patterns:
        if pattern in request_lower:
            return "memory"

    # Research patterns
    research_patterns = [
        "search for", "look up", "find out", "research",
        "what is the latest", "news about",
    ]
    for pattern in research_patterns:
        if pattern in request_lower:
            return "research"

    # Code patterns
    code_patterns = [
        "write a function", "write a script", "code",
        "program", "debug", "fix the bug",
        "python", "javascript",
    ]
    for pattern in code_patterns:
        if pattern in request_lower:
            return "code"

    # Writing patterns
    writing_patterns = [
        "write a document", "write a report", "documentation",
        "summarize", "draft",
    ]
    for pattern in writing_patterns:
        if pattern in request_lower:
            return "writing"

    # Default: handle directly
    return "direct"
