"""Agent creation with three-tier memory system.

Memory Architecture:
- Tier 1 (Hot): MEMORY.md — always loaded, ~300 lines
- Tier 2 (Vault): memory/ — structured markdown, append-only
- Tier 3 (Semantic): Vector search over vault files

Model Management:
- Pulls requested model automatically if not available
- Falls back through capability-based model chains
- Multi-modal support with vision model fallbacks

Handoff Protocol maintains continuity across sessions.
"""

import logging
from typing import TYPE_CHECKING, Optional, Union

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.ollama import Ollama

from config import check_ollama_model_available, settings
from timmy.prompts import get_system_prompt
from timmy.tools import create_full_toolkit

if TYPE_CHECKING:
    from timmy.backends import ClaudeBackend, GrokBackend, TimmyAirLLMAgent

logger = logging.getLogger(__name__)

# Fallback chain for text/tool models (in order of preference)
DEFAULT_MODEL_FALLBACKS = [
    "llama3.1:8b-instruct",
    "llama3.1",
    "qwen2.5:14b",
    "qwen2.5:7b",
    "llama3.2:3b",
]

# Fallback chain for vision models
VISION_MODEL_FALLBACKS = [
    "llama3.2:3b",
    "llava:7b",
    "qwen2.5-vl:3b",
    "moondream:1.8b",
]

# Union type for callers that want to hint the return type.
TimmyAgent = Union[Agent, "TimmyAirLLMAgent", "GrokBackend", "ClaudeBackend"]

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


def _check_model_available(model_name: str) -> bool:
    """Check if an Ollama model is available locally."""
    return check_ollama_model_available(model_name)


def _pull_model(model_name: str) -> bool:
    """Attempt to pull a model from Ollama.
    
    Returns:
        True if successful or model already exists
    """
    try:
        import urllib.request
        import json
        
        logger.info("Pulling model: %s", model_name)
        
        url = settings.ollama_url.replace("localhost", "127.0.0.1")
        req = urllib.request.Request(
            f"{url}/api/pull",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"name": model_name, "stream": False}).encode(),
        )
        
        with urllib.request.urlopen(req, timeout=300) as response:
            if response.status == 200:
                logger.info("Successfully pulled model: %s", model_name)
                return True
            else:
                logger.error("Failed to pull %s: HTTP %s", model_name, response.status)
                return False
                
    except Exception as exc:
        logger.error("Error pulling model %s: %s", model_name, exc)
        return False


def _resolve_model_with_fallback(
    requested_model: Optional[str] = None,
    require_vision: bool = False,
    auto_pull: bool = True,
) -> tuple[str, bool]:
    """Resolve model with automatic pulling and fallback.
    
    Args:
        requested_model: Preferred model to use
        require_vision: Whether the model needs vision capabilities
        auto_pull: Whether to attempt pulling missing models
        
    Returns:
        Tuple of (model_name, is_fallback)
    """
    model = requested_model or settings.ollama_model
    
    # Check if requested model is available
    if _check_model_available(model):
        logger.debug("Using available model: %s", model)
        return model, False
    
    # Try to pull the requested model
    if auto_pull:
        logger.info("Model %s not available locally, attempting to pull...", model)
        if _pull_model(model):
            return model, False
        logger.warning("Failed to pull %s, checking fallbacks...", model)
    
    # Use appropriate fallback chain
    fallback_chain = VISION_MODEL_FALLBACKS if require_vision else DEFAULT_MODEL_FALLBACKS
    
    for fallback_model in fallback_chain:
        if _check_model_available(fallback_model):
            logger.warning(
                "Using fallback model %s (requested: %s)",
                fallback_model, model
            )
            return fallback_model, True
        
        # Try to pull the fallback
        if auto_pull and _pull_model(fallback_model):
            logger.info(
                "Pulled and using fallback model %s (requested: %s)",
                fallback_model, model
            )
            return fallback_model, True
    
    # Absolute last resort - return the requested model and hope for the best
    logger.error(
        "No models available in fallback chain. Requested: %s",
        model
    )
    return model, False


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

    configured = settings.timmy_model_backend  # "ollama" | "airllm" | "grok" | "claude" | "auto"
    if configured != "auto":
        return configured

    # "auto" path — lazy import to keep startup fast and tests clean.
    from timmy.backends import airllm_available, claude_available, grok_available, is_apple_silicon
    if is_apple_silicon() and airllm_available():
        return "airllm"
    return "ollama"


def create_timmy(
    db_file: str = "timmy.db",
    backend: str | None = None,
    model_size: str | None = None,
) -> TimmyAgent:
    """Instantiate the agent — Ollama or AirLLM, same public interface.

    Args:
        db_file:    SQLite file for Agno conversation memory (Ollama path only).
        backend:    "ollama" | "airllm" | "auto" | None (reads config/env).
        model_size: AirLLM size — "8b" | "70b" | "405b" | None (reads config).

    Returns an Agno Agent or backend-specific agent — all expose
    print_response(message, stream).
    """
    resolved = _resolve_backend(backend)
    size = model_size or settings.airllm_model_size

    if resolved == "claude":
        from timmy.backends import ClaudeBackend
        return ClaudeBackend()

    if resolved == "grok":
        from timmy.backends import GrokBackend
        return GrokBackend()

    if resolved == "airllm":
        from timmy.backends import TimmyAirLLMAgent
        return TimmyAirLLMAgent(model_size=size)

    # Default: Ollama via Agno.
    # Resolve model with automatic pulling and fallback
    model_name, is_fallback = _resolve_model_with_fallback(
        requested_model=None,
        require_vision=False,
        auto_pull=True,
    )

    # If Ollama is completely unreachable, fall back to Claude if available
    if not _check_model_available(model_name):
        from timmy.backends import claude_available
        if claude_available():
            logger.warning(
                "Ollama unreachable — falling back to Claude backend"
            )
            from timmy.backends import ClaudeBackend
            return ClaudeBackend()

    if is_fallback:
        logger.info("Using fallback model %s (requested was unavailable)", model_name)
    
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
            # Truncate if too long — smaller budget for small models
            # since the expanded prompt (roster, guardrails) uses more tokens
            max_context = 2000 if not use_tools else 8000
            if len(memory_context) > max_context:
                memory_context = memory_context[:max_context] + "\n... [truncated]"
            full_prompt = f"{base_prompt}\n\n## Memory Context\n\n{memory_context}"
        else:
            full_prompt = base_prompt
    except Exception as exc:
        logger.warning("Failed to load memory context: %s", exc)
        full_prompt = base_prompt

    return Agent(
        name="Agent",
        model=Ollama(id=model_name, host=settings.ollama_url, timeout=300),
        db=SqliteDb(db_file=db_file),
        description=full_prompt,
        add_history_to_context=True,
        num_history_runs=20,
        markdown=True,
        tools=[tools] if tools else None,
        show_tool_calls=True if use_tools else False,
        tool_call_limit=settings.max_agent_steps if use_tools else None,
        telemetry=settings.telemetry_enabled,
    )


class TimmyWithMemory:
    """Agent wrapper with explicit three-tier memory management."""
    
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
