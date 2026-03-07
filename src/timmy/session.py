"""Persistent chat session for Timmy.

Holds a singleton Agno Agent and a stable session_id so conversation
history persists across HTTP requests via Agno's SQLite storage.

This is the primary entry point for dashboard chat — instead of
creating a new agent per request, we reuse a single instance and
let Agno's session_id mechanism handle conversation continuity.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Default session ID for the dashboard (stable across requests)
_DEFAULT_SESSION_ID = "dashboard"

# Module-level singleton agent (lazy-initialized, reused for all requests)
_agent = None

# ---------------------------------------------------------------------------
# Response sanitization patterns
# ---------------------------------------------------------------------------

# Matches raw JSON tool calls: {"name": "python", "parameters": {...}}
_TOOL_CALL_JSON = re.compile(
    r'\{\s*"name"\s*:\s*"[^"]+?"\s*,\s*"parameters"\s*:\s*\{.*?\}\s*\}',
    re.DOTALL,
)

# Matches function-call-style text: memory_search(query="...") etc.
_FUNC_CALL_TEXT = re.compile(
    r'\b(?:memory_search|web_search|shell|python|read_file|write_file|list_files|calculator)'
    r'\s*\([^)]*\)',
)

# Matches chain-of-thought narration lines the model should keep internal
_COT_PATTERNS = [
    re.compile(r"^(?:Since |Using |Let me |I'll use |I will use |Here's a possible ).*$", re.MULTILINE),
    re.compile(r"^(?:I found a relevant |This context suggests ).*$", re.MULTILINE),
]


def _get_agent():
    """Lazy-initialize the singleton agent."""
    global _agent
    if _agent is None:
        from timmy.agent import create_timmy
        try:
            _agent = create_timmy()
            logger.info("Session: Timmy agent initialized (singleton)")
        except Exception as exc:
            logger.error("Session: Failed to create Timmy agent: %s", exc)
            raise
    return _agent


def chat(message: str, session_id: Optional[str] = None) -> str:
    """Send a message to Timmy and get a response.

    Uses a persistent agent and session_id so Agno's SQLite history
    provides multi-turn conversation context.

    Args:
        message:    The user's message.
        session_id: Optional session identifier (defaults to "dashboard").

    Returns:
        The agent's response text.
    """
    sid = session_id or _DEFAULT_SESSION_ID
    agent = _get_agent()

    # Pre-processing: extract user facts
    _extract_facts(message)

    # Run with session_id so Agno retrieves history from SQLite
    run = agent.run(message, stream=False, session_id=sid)
    response_text = run.content if hasattr(run, "content") else str(run)

    # Post-processing: clean up any leaked tool calls or chain-of-thought
    response_text = _clean_response(response_text)

    return response_text


def reset_session(session_id: Optional[str] = None) -> None:
    """Reset a session (clear conversation context).

    This clears the ConversationManager state. Agno's SQLite history
    is not cleared — that provides long-term continuity.
    """
    sid = session_id or _DEFAULT_SESSION_ID
    try:
        from timmy.conversation import conversation_manager
        conversation_manager.clear_context(sid)
    except Exception as exc:
        logger.debug("Session: context clear failed for %s: %s", sid, exc)


def _extract_facts(message: str) -> None:
    """Extract user facts from message and persist to memory system.

    Ported from TimmyWithMemory._extract_and_store_facts().
    Runs as a best-effort post-processor — failures are logged, not raised.
    """
    try:
        from timmy.conversation import conversation_manager
        name = conversation_manager.extract_user_name(message)
        if name:
            try:
                from timmy.memory_system import memory_system
                memory_system.update_user_fact("Name", name)
                logger.info("Session: Learned user name: %s", name)
            except Exception as exc:
                logger.debug("Session: fact persist failed: %s", exc)
    except Exception as exc:
        logger.debug("Session: Fact extraction skipped: %s", exc)


def _clean_response(text: str) -> str:
    """Remove hallucinated tool calls and chain-of-thought narration.

    Small models sometimes output raw JSON tool calls or narrate their
    internal reasoning instead of just answering. This strips those
    artifacts from the response.
    """
    if not text:
        return text

    # Strip JSON tool call blocks
    text = _TOOL_CALL_JSON.sub("", text)

    # Strip function-call-style text
    text = _FUNC_CALL_TEXT.sub("", text)

    # Strip chain-of-thought narration lines
    for pattern in _COT_PATTERNS:
        text = pattern.sub("", text)

    # Clean up leftover blank lines and whitespace
    lines = [line for line in text.split("\n") if line.strip()]
    text = "\n".join(lines)

    return text.strip()
