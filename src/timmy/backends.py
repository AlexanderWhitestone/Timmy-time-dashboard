"""LLM backends — AirLLM (local big models), Grok (xAI), and Claude (Anthropic).

Provides drop-in replacements for the Agno Agent that expose the same
run(message, stream) → RunResult interface used by the dashboard and the
print_response(message, stream) interface used by the CLI.

Backends:
  - TimmyAirLLMAgent: Local 8B/70B/405B via AirLLM (Apple Silicon or PyTorch)
  - GrokBackend: xAI Grok API via OpenAI-compatible SDK (opt-in premium)
  - ClaudeBackend: Anthropic Claude API — lightweight cloud fallback

No cloud by default.  No telemetry.  Sats are sovereignty, boss.
"""

import logging
import platform
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from timmy.prompts import TIMMY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# HuggingFace model IDs for each supported size.
_AIRLLM_MODELS: dict[str, str] = {
    "8b":   "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "70b":  "meta-llama/Meta-Llama-3.1-70B-Instruct",
    "405b": "meta-llama/Meta-Llama-3.1-405B-Instruct",
}

ModelSize = Literal["8b", "70b", "405b"]


@dataclass
class RunResult:
    """Minimal Agno-compatible run result — carries the model's response text."""
    content: str


def is_apple_silicon() -> bool:
    """Return True when running on an M-series Mac (arm64 Darwin)."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def airllm_available() -> bool:
    """Return True when the airllm package is importable."""
    try:
        import airllm  # noqa: F401
        return True
    except ImportError:
        return False


class TimmyAirLLMAgent:
    """Thin AirLLM wrapper compatible with both dashboard and CLI call sites.

    Exposes:
      run(message, stream)           → RunResult(content=...)  [dashboard]
      print_response(message, stream) → None                   [CLI]

    Maintains a rolling 10-turn in-memory history so Timmy remembers the
    conversation within a session — no SQLite needed at this layer.
    """

    def __init__(self, model_size: str = "70b") -> None:
        model_id = _AIRLLM_MODELS.get(model_size)
        if model_id is None:
            raise ValueError(
                f"Unknown model size {model_size!r}. "
                f"Choose from: {list(_AIRLLM_MODELS)}"
            )

        if is_apple_silicon():
            from airllm import AirLLMMLX  # type: ignore[import]
            self._model = AirLLMMLX(model_id)
        else:
            from airllm import AutoModel  # type: ignore[import]
            self._model = AutoModel.from_pretrained(model_id)

        self._history: list[str] = []
        self._model_size = model_size

    # ── public interface (mirrors Agno Agent) ────────────────────────────────

    def run(self, message: str, *, stream: bool = False) -> RunResult:
        """Run inference and return a structured result (matches Agno Agent.run()).

        `stream` is accepted for API compatibility; AirLLM always generates
        the full output in one pass.
        """
        prompt = self._build_prompt(message)

        input_tokens = self._model.tokenizer(
            [prompt],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=2048,
        )
        output = self._model.generate(
            **input_tokens,
            max_new_tokens=512,
            use_cache=True,
            do_sample=True,
            temperature=0.7,
        )

        # Decode only the newly generated tokens, not the prompt.
        input_len = input_tokens["input_ids"].shape[1]
        response = self._model.tokenizer.decode(
            output[0][input_len:], skip_special_tokens=True
        ).strip()

        self._history.append(f"User: {message}")
        self._history.append(f"Timmy: {response}")

        return RunResult(content=response)

    def print_response(self, message: str, *, stream: bool = True) -> None:
        """Run inference and render the response to stdout (CLI interface)."""
        result = self.run(message, stream=stream)
        self._render(result.content)

    # ── private helpers ──────────────────────────────────────────────────────

    def _build_prompt(self, message: str) -> str:
        context = TIMMY_SYSTEM_PROMPT + "\n\n"
        # Include the last 10 turns (5 exchanges) for continuity.
        if self._history:
            context += "\n".join(self._history[-10:]) + "\n\n"
        return context + f"User: {message}\nTimmy:"

    @staticmethod
    def _render(text: str) -> None:
        """Print response with rich markdown when available, plain text otherwise."""
        try:
            from rich.console import Console
            from rich.markdown import Markdown
            Console().print(Markdown(text))
        except ImportError:
            print(text)


# ── Grok (xAI) Backend ─────────────────────────────────────────────────────
# Premium cloud augmentation — opt-in only, never the default path.

# Available Grok models (configurable via GROK_DEFAULT_MODEL)
GROK_MODELS: dict[str, str] = {
    "grok-3-fast": "grok-3-fast",
    "grok-3": "grok-3",
    "grok-3-mini": "grok-3-mini",
    "grok-3-mini-fast": "grok-3-mini-fast",
}


@dataclass
class GrokUsageStats:
    """Tracks Grok API usage for cost monitoring and Spark logging."""
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_latency_ms: float = 0.0
    errors: int = 0
    last_request_at: Optional[float] = None

    @property
    def estimated_cost_sats(self) -> int:
        """Rough cost estimate in sats based on token usage."""
        # ~$5/1M input tokens, ~$15/1M output tokens for Grok
        # At ~$100k/BTC, 1 sat ≈ $0.001
        input_cost = (self.total_prompt_tokens / 1_000_000) * 5
        output_cost = (self.total_completion_tokens / 1_000_000) * 15
        total_usd = input_cost + output_cost
        return int(total_usd / 0.001)  # Convert to sats


class GrokBackend:
    """xAI Grok backend — premium cloud augmentation for frontier reasoning.

    Uses the OpenAI-compatible SDK to connect to xAI's API.
    Only activated when GROK_ENABLED=true and XAI_API_KEY is set.

    Exposes the same interface as TimmyAirLLMAgent and Agno Agent:
      run(message, stream)           → RunResult  [dashboard]
      print_response(message, stream) → None       [CLI]
      health_check()                 → dict        [monitoring]
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        from config import settings

        self._api_key = api_key or settings.xai_api_key
        self._model = model or settings.grok_default_model
        self._history: list[dict[str, str]] = []
        self.stats = GrokUsageStats()

        if not self._api_key:
            logger.warning(
                "GrokBackend created without XAI_API_KEY — "
                "calls will fail until key is configured"
            )

    def _get_client(self):
        """Create OpenAI client configured for xAI endpoint."""
        import httpx
        from openai import OpenAI

        return OpenAI(
            api_key=self._api_key,
            base_url="https://api.x.ai/v1",
            timeout=httpx.Timeout(300.0),
        )

    async def _get_async_client(self):
        """Create async OpenAI client configured for xAI endpoint."""
        import httpx
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.x.ai/v1",
            timeout=httpx.Timeout(300.0),
        )

    # ── Public interface (mirrors Agno Agent) ─────────────────────────────

    def run(self, message: str, *, stream: bool = False) -> RunResult:
        """Synchronous inference via Grok API.

        Args:
            message: User prompt
            stream: Accepted for API compat; Grok returns full response

        Returns:
            RunResult with response content
        """
        if not self._api_key:
            return RunResult(
                content="Grok is not configured. Set XAI_API_KEY to enable."
            )

        start = time.time()
        messages = self._build_messages(message)

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.7,
            )

            content = response.choices[0].message.content or ""
            latency_ms = (time.time() - start) * 1000

            # Track usage
            self.stats.total_requests += 1
            self.stats.total_latency_ms += latency_ms
            self.stats.last_request_at = time.time()
            if response.usage:
                self.stats.total_prompt_tokens += response.usage.prompt_tokens
                self.stats.total_completion_tokens += response.usage.completion_tokens

            # Update conversation history
            self._history.append({"role": "user", "content": message})
            self._history.append({"role": "assistant", "content": content})
            # Keep last 10 turns
            if len(self._history) > 20:
                self._history = self._history[-20:]

            logger.info(
                "Grok response: %d tokens in %.0fms (model=%s)",
                response.usage.completion_tokens if response.usage else 0,
                latency_ms,
                self._model,
            )

            return RunResult(content=content)

        except Exception as exc:
            self.stats.errors += 1
            logger.error("Grok API error: %s", exc)
            return RunResult(
                content=f"Grok temporarily unavailable: {exc}"
            )

    async def arun(self, message: str) -> RunResult:
        """Async inference via Grok API — used by cascade router and tools."""
        if not self._api_key:
            return RunResult(
                content="Grok is not configured. Set XAI_API_KEY to enable."
            )

        start = time.time()
        messages = self._build_messages(message)

        try:
            client = await self._get_async_client()
            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.7,
            )

            content = response.choices[0].message.content or ""
            latency_ms = (time.time() - start) * 1000

            # Track usage
            self.stats.total_requests += 1
            self.stats.total_latency_ms += latency_ms
            self.stats.last_request_at = time.time()
            if response.usage:
                self.stats.total_prompt_tokens += response.usage.prompt_tokens
                self.stats.total_completion_tokens += response.usage.completion_tokens

            # Update conversation history
            self._history.append({"role": "user", "content": message})
            self._history.append({"role": "assistant", "content": content})
            if len(self._history) > 20:
                self._history = self._history[-20:]

            logger.info(
                "Grok async response: %d tokens in %.0fms (model=%s)",
                response.usage.completion_tokens if response.usage else 0,
                latency_ms,
                self._model,
            )

            return RunResult(content=content)

        except Exception as exc:
            self.stats.errors += 1
            logger.error("Grok async API error: %s", exc)
            return RunResult(
                content=f"Grok temporarily unavailable: {exc}"
            )

    def print_response(self, message: str, *, stream: bool = True) -> None:
        """Run inference and render the response to stdout (CLI interface)."""
        result = self.run(message, stream=stream)
        try:
            from rich.console import Console
            from rich.markdown import Markdown
            Console().print(Markdown(result.content))
        except ImportError:
            print(result.content)

    def health_check(self) -> dict:
        """Check Grok API connectivity and return status."""
        if not self._api_key:
            return {
                "ok": False,
                "error": "XAI_API_KEY not configured",
                "backend": "grok",
                "model": self._model,
            }

        try:
            client = self._get_client()
            # Lightweight check — list models
            client.models.list()
            return {
                "ok": True,
                "error": None,
                "backend": "grok",
                "model": self._model,
                "stats": {
                    "total_requests": self.stats.total_requests,
                    "estimated_cost_sats": self.stats.estimated_cost_sats,
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "backend": "grok",
                "model": self._model,
            }

    @property
    def estimated_cost(self) -> int:
        """Return estimated cost in sats for all requests so far."""
        return self.stats.estimated_cost_sats

    # ── Private helpers ───────────────────────────────────────────────────

    def _build_messages(self, message: str) -> list[dict[str, str]]:
        """Build the messages array for the API call."""
        messages = [{"role": "system", "content": TIMMY_SYSTEM_PROMPT}]
        # Include conversation history for context
        messages.extend(self._history[-10:])
        messages.append({"role": "user", "content": message})
        return messages


# ── Module-level Grok singleton ─────────────────────────────────────────────

_grok_backend: Optional[GrokBackend] = None


def get_grok_backend() -> GrokBackend:
    """Get or create the Grok backend singleton."""
    global _grok_backend
    if _grok_backend is None:
        _grok_backend = GrokBackend()
    return _grok_backend


def grok_available() -> bool:
    """Return True when Grok is enabled and API key is configured."""
    try:
        from config import settings
        return settings.grok_enabled and bool(settings.xai_api_key)
    except Exception:
        return False


# ── Claude (Anthropic) Backend ─────────────────────────────────────────────
# Lightweight cloud fallback — used when Ollama is offline and the user
# has set ANTHROPIC_API_KEY.  Follows the same sovereign-first philosophy:
# never the default, only activated explicitly or as a last-resort fallback.

CLAUDE_MODELS: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
}


class ClaudeBackend:
    """Anthropic Claude backend — cloud fallback when local models are offline.

    Uses the official Anthropic SDK.  Same interface as GrokBackend and
    TimmyAirLLMAgent:
      run(message, stream)           → RunResult  [dashboard]
      print_response(message, stream) → None       [CLI]
      health_check()                 → dict        [monitoring]
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        from config import settings

        self._api_key = api_key or settings.anthropic_api_key
        raw_model = model or settings.claude_model
        # Allow short names like "haiku" / "sonnet" / "opus"
        self._model = CLAUDE_MODELS.get(raw_model, raw_model)
        self._history: list[dict[str, str]] = []

        if not self._api_key:
            logger.warning(
                "ClaudeBackend created without ANTHROPIC_API_KEY — "
                "calls will fail until key is configured"
            )

    def _get_client(self):
        """Create Anthropic client."""
        import anthropic

        return anthropic.Anthropic(api_key=self._api_key)

    # ── Public interface (mirrors Agno Agent) ─────────────────────────────

    def run(self, message: str, *, stream: bool = False, **kwargs) -> RunResult:
        """Synchronous inference via Claude API."""
        if not self._api_key:
            return RunResult(
                content="Claude is not configured. Set ANTHROPIC_API_KEY to enable."
            )

        start = time.time()
        messages = self._build_messages(message)

        try:
            client = self._get_client()
            response = client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=TIMMY_SYSTEM_PROMPT,
                messages=messages,
            )

            content = response.content[0].text if response.content else ""
            latency_ms = (time.time() - start) * 1000

            # Update conversation history
            self._history.append({"role": "user", "content": message})
            self._history.append({"role": "assistant", "content": content})
            if len(self._history) > 20:
                self._history = self._history[-20:]

            logger.info(
                "Claude response: %d chars in %.0fms (model=%s)",
                len(content),
                latency_ms,
                self._model,
            )

            return RunResult(content=content)

        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            return RunResult(
                content=f"Claude temporarily unavailable: {exc}"
            )

    def print_response(self, message: str, *, stream: bool = True) -> None:
        """Run inference and render the response to stdout (CLI interface)."""
        result = self.run(message, stream=stream)
        try:
            from rich.console import Console
            from rich.markdown import Markdown
            Console().print(Markdown(result.content))
        except ImportError:
            print(result.content)

    def health_check(self) -> dict:
        """Check Claude API connectivity."""
        if not self._api_key:
            return {
                "ok": False,
                "error": "ANTHROPIC_API_KEY not configured",
                "backend": "claude",
                "model": self._model,
            }
        try:
            client = self._get_client()
            # Lightweight ping — tiny completion
            client.messages.create(
                model=self._model,
                max_tokens=4,
                messages=[{"role": "user", "content": "ping"}],
            )
            return {"ok": True, "error": None, "backend": "claude", "model": self._model}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "backend": "claude", "model": self._model}

    # ── Private helpers ───────────────────────────────────────────────────

    def _build_messages(self, message: str) -> list[dict[str, str]]:
        """Build the messages array for the API call."""
        messages = list(self._history[-10:])
        messages.append({"role": "user", "content": message})
        return messages


# ── Module-level Claude singleton ──────────────────────────────────────────

_claude_backend: Optional[ClaudeBackend] = None


def get_claude_backend() -> ClaudeBackend:
    """Get or create the Claude backend singleton."""
    global _claude_backend
    if _claude_backend is None:
        _claude_backend = ClaudeBackend()
    return _claude_backend


def claude_available() -> bool:
    """Return True when Anthropic API key is configured."""
    try:
        from config import settings
        return bool(settings.anthropic_api_key)
    except Exception:
        return False
