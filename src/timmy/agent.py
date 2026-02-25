"""Timmy agent creation with multi-layer memory system.

Integrates Agno's Agent with our custom memory layers:
- Working Memory (immediate context)
- Short-term Memory (Agno SQLite)  
- Long-term Memory (facts/preferences)
"""

from typing import TYPE_CHECKING, Union

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.ollama import Ollama

from config import settings
from timmy.prompts import TIMMY_SYSTEM_PROMPT
from timmy.tools import create_full_toolkit

if TYPE_CHECKING:
    from timmy.backends import TimmyAirLLMAgent

# Union type for callers that want to hint the return type.
TimmyAgent = Union[Agent, "TimmyAirLLMAgent"]


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
    # Add tools for sovereign agent capabilities
    tools = create_full_toolkit()
    
    return Agent(
        name="Timmy",
        model=Ollama(id=settings.ollama_model, host=settings.ollama_url),
        db=SqliteDb(db_file=db_file),
        description=TIMMY_SYSTEM_PROMPT,
        add_history_to_context=True,
        num_history_runs=20,  # Increased for better conversational context
        markdown=True,
        tools=[tools] if tools else None,
        telemetry=settings.telemetry_enabled,
    )


class TimmyWithMemory:
    """Timmy wrapper with explicit memory layer management.
    
    This class wraps the Agno Agent and adds:
    - Working memory tracking
    - Long-term memory storage/retrieval
    - Context injection from memory layers
    """
    
    def __init__(self, db_file: str = "timmy.db") -> None:
        from timmy.memory_layers import memory_manager
        
        self.agent = create_timmy(db_file=db_file)
        self.memory = memory_manager
        self.memory.start_session()
        
        # Inject user context if available
        self._inject_context()
    
    def _inject_context(self) -> None:
        """Inject relevant memory context into system prompt."""
        context = self.memory.get_context_for_prompt()
        if context:
            # Append context to system prompt
            original_description = self.agent.description
            self.agent.description = f"{original_description}\n\n## User Context\n{context}"
    
    def run(self, message: str, stream: bool = False) -> object:
        """Run with memory tracking."""
        # Get relevant memories
        relevant = self.memory.get_relevant_memories(message)
        
        # Enhance message with context if relevant
        enhanced_message = message
        if relevant:
            context_str = "\n".join(f"- {r}" for r in relevant[:3])
            enhanced_message = f"[Context: {context_str}]\n\n{message}"
        
        # Run agent
        result = self.agent.run(enhanced_message, stream=stream)
        
        # Extract response content
        response_text = result.content if hasattr(result, "content") else str(result)
        
        # Track in memory
        tool_calls = getattr(result, "tool_calls", None)
        self.memory.add_exchange(message, response_text, tool_calls)
        
        return result
    
    def chat(self, message: str) -> str:
        """Simple chat interface that returns string response."""
        result = self.run(message, stream=False)
        return result.content if hasattr(result, "content") else str(result)
