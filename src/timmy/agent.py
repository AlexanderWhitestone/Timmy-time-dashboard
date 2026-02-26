"""Timmy agent creation with three-tier memory system.

Memory Architecture:
- Tier 1 (Hot): MEMORY.md — always loaded, ~300 lines
- Tier 2 (Vault): memory/ — structured markdown, append-only
- Tier 3 (Semantic): Vector search over vault files

Handoff Protocol maintains continuity across sessions.
"""

import logging
from typing import TYPE_CHECKING, Union

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.ollama import Ollama

from config import settings
from timmy.prompts import get_system_prompt
from timmy.tools import create_full_toolkit

if TYPE_CHECKING:
    from timmy.backends import TimmyAirLLMAgent

logger = logging.getLogger(__name__)

# Union type for callers that want to hint the return type.
TimmyAgent = Union[Agent, "TimmyAirLLMAgent"]

# Models known to be too small for reliable tool calling.
# These hallucinate tool calls as text, invoke tools randomly,
# and leak raw JSON into responses.
_SMALL_MODEL_PATTERNS = (
    "llama3.2",
    "phi-3",
    "gemma:2b",
    "tinyllama",
    "qwen2:0.5b",
    "qwen2:1.5b",
)


def _model_supports_tools(model_name: str) -> bool:
    """Check if the configured model can reliably handle tool calling.

    Small models (< 7B) tend to hallucinate tool calls as text or invoke
    them randomly.  For these models, it's better to run tool-free and let
    the model answer directly from its training data.
    """
    model_lower = model_name.lower()
    for pattern in _SMALL_MODEL_PATTERNS:
        if pattern in model_lower:
            return False
    return True


def _resolve_backend(requested: str | None) -> str:
    """Return the backend name to use, resolving 'auto' and explicit overrides.

    Priority (highest → lowest):
      1. CLI flag passed directly to create_timmy()
      2. TIMMY_MODEL_BACKEND env var / .env setting
      3. 'ollama' (safe default — no surprises)

    'auto' triggers Apple Silicon detection: uses AirLLM if both
    is_apple_silicon() and airllm_available() return True.
    """
    if requested is not None:
        return requested

    configured = settings.timmy_model_backend  # "ollama" | "airllm" | "auto"
    if configured != "auto":
        return configured

    # "auto" path — lazy import to keep startup fast and tests clean.
    from timmy.backends import airllm_available, is_apple_silicon
    if is_apple_silicon() and airllm_available():
        return "airllm"
    return "ollama"


def create_timmy(
    db_file: str = "timmy.db",
    backend: str | None = None,
    model_size: str | None = None,
) -> TimmyAgent:
    """Instantiate Timmy — Ollama or AirLLM, same public interface either way.

    Args:
        db_file:    SQLite file for Agno conversation memory (Ollama path only).
        backend:    "ollama" | "airllm" | "auto" | None (reads config/env).
        model_size: AirLLM size — "8b" | "70b" | "405b" | None (reads config).

    Returns an Agno Agent (Ollama) or TimmyAirLLMAgent — both expose
    print_response(message, stream).
    """
    resolved = _resolve_backend(backend)
    size = model_size or settings.airllm_model_size

    if resolved == "airllm":
        from timmy.backends import TimmyAirLLMAgent
        return TimmyAirLLMAgent(model_size=size)

    # Default: Ollama via Agno.
    model_name = settings.ollama_model
    use_tools = _model_supports_tools(model_name)

    # Conditionally include tools — small models get none
    tools = create_full_toolkit() if use_tools else None
    if not use_tools:
        logger.info("Tools disabled for model %s (too small for reliable tool calling)", model_name)

    # Select prompt tier based on tool capability
    base_prompt = get_system_prompt(tools_enabled=use_tools)

    # Try to load memory context
    try:
        from timmy.memory_system import memory_system
        memory_context = memory_system.get_system_context()
        if memory_context:
            # Truncate if too long (keep under token limit)
            max_context = 4000 if not use_tools else 8000
            if len(memory_context) > max_context:
                memory_context = memory_context[:max_context] + "\n... [truncated]"
            full_prompt = f"{base_prompt}\n\n## Memory Context\n\n{memory_context}"
        else:
            full_prompt = base_prompt
    except Exception as exc:
        logger.warning("Failed to load memory context: %s", exc)
        full_prompt = base_prompt

    return Agent(
        name="Timmy",
        model=Ollama(id=model_name, host=settings.ollama_url),
        db=SqliteDb(db_file=db_file),
        description=full_prompt,
        add_history_to_context=True,
        num_history_runs=20,
        markdown=True,
        tools=[tools] if tools else None,
        show_tool_calls=False,
        telemetry=settings.telemetry_enabled,
    )


class TimmyWithMemory:
    """Timmy wrapper with explicit three-tier memory management."""
    
    def __init__(self, db_file: str = "timmy.db") -> None:
        from timmy.memory_system import memory_system
        
        self.agent = create_timmy(db_file=db_file)
        self.memory = memory_system
        self.session_active = True
        
        # Store initial context for reference
        self.initial_context = self.memory.get_system_context()
    
    def chat(self, message: str) -> str:
        """Simple chat interface that tracks in memory."""
        # Check for user facts to extract
        self._extract_and_store_facts(message)
        
        # Run agent
        result = self.agent.run(message, stream=False)
        response_text = result.content if hasattr(result, "content") else str(result)
        
        return response_text
    
    def _extract_and_store_facts(self, message: str) -> None:
        """Extract user facts from message and store in memory."""
        message_lower = message.lower()
        
        # Extract name
        name_patterns = [
            ("my name is ", 11),
            ("i'm ", 4),
            ("i am ", 5),
            ("call me ", 8),
        ]
        
        for pattern, offset in name_patterns:
            if pattern in message_lower:
                idx = message_lower.find(pattern) + offset
                name = message[idx:].strip().split()[0].strip(".,!?;:()\"'").capitalize()
                if name and len(name) > 1 and name.lower() not in ("the", "a", "an"):
                    self.memory.update_user_fact("Name", name)
                    self.memory.record_decision(f"Learned user's name: {name}")
                break
        
        # Extract preferences
        pref_patterns = [
            ("i like ", "Likes"),
            ("i love ", "Loves"),
            ("i prefer ", "Prefers"),
            ("i don't like ", "Dislikes"),
            ("i hate ", "Dislikes"),
        ]
        
        for pattern, category in pref_patterns:
            if pattern in message_lower:
                idx = message_lower.find(pattern) + len(pattern)
                pref = message[idx:].strip().split(".")[0].strip()
                if pref and len(pref) > 3:
                    self.memory.record_open_item(f"User {category.lower()}: {pref}")
                break
    
    def end_session(self, summary: str = "Session completed") -> None:
        """End session and write handoff."""
        if self.session_active:
            self.memory.end_session(summary)
            self.session_active = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_session()
        return False
