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
        num_history_runs=10,
        markdown=True,
        tools=tools,
    )
