from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Display name for the primary agent — override with AGENT_NAME env var
    agent_name: str = "Agent"

    # Ollama host — override with OLLAMA_URL env var or .env file
    ollama_url: str = "http://localhost:11434"

    # LLM model passed to Agno/Ollama — override with OLLAMA_MODEL
    # llama3.1:8b-instruct is used instead of llama3.2 because it is
    # specifically fine-tuned for reliable tool/function calling.
    # llama3.2 (3B) hallucinated tool output consistently in testing.
    # Fallback: qwen2.5:14b if llama3.1:8b-instruct not available.
    ollama_model: str = "llama3.1:8b-instruct"

    # Set DEBUG=true to enable /docs and /redoc (disabled by default)
    debug: bool = False

    # Telegram bot token — set via TELEGRAM_TOKEN env var or the /telegram/setup endpoint
    telegram_token: str = ""

    # Discord bot token — set via DISCORD_TOKEN env var or the /discord/setup endpoint
    discord_token: str = ""

    # ── Celery / Redis ──────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_enabled: bool = True

    # ── AirLLM / backend selection ───────────────────────────────────────────
    # "ollama"  — always use Ollama (default, safe everywhere)
    # "airllm"  — always use AirLLM (requires pip install ".[bigbrain]")
    # "auto"    — use AirLLM on Apple Silicon if airllm is installed,
    #             fall back to Ollama otherwise
    timmy_model_backend: Literal["ollama", "airllm", "grok", "claude", "auto"] = "ollama"

    # AirLLM model size when backend is airllm or auto.
    # Larger = smarter, but needs more RAM / disk.
    # 8b  ~16 GB  |  70b  ~140 GB  |  405b  ~810 GB
    airllm_model_size: Literal["8b", "70b", "405b"] = "70b"

    # ── Grok (xAI) — opt-in premium cloud backend ────────────────────────
    # Grok is a premium augmentation layer — local-first ethos preserved.
    # Only used when explicitly enabled and query complexity warrants it.
    grok_enabled: bool = False
    xai_api_key: str = ""
    grok_default_model: str = "grok-3-fast"
    grok_max_sats_per_query: int = 200
    grok_free: bool = False  # Skip Lightning invoice when user has own API key

    # ── Claude (Anthropic) — cloud fallback backend ────────────────────────
    # Used when Ollama is offline and local inference isn't available.
    # Set ANTHROPIC_API_KEY to enable.  Default model is Haiku (fast + cheap).
    anthropic_api_key: str = ""
    claude_model: str = "haiku"

    # ── Spark Intelligence ────────────────────────────────────────────────
    # Enable/disable the Spark cognitive layer.
    # When enabled, Spark captures swarm events, runs EIDOS predictions,
    # consolidates memories, and generates advisory recommendations.
    spark_enabled: bool = True

    # ── Git / DevOps ──────────────────────────────────────────────────────
    git_default_repo_dir: str = "~/repos"

    # Repository root - auto-detected but can be overridden
    # This is the main project directory where .git lives
    repo_root: str = ""

    # ── Creative — Image Generation (Pixel) ───────────────────────────────
    flux_model_id: str = "black-forest-labs/FLUX.1-schnell"
    image_output_dir: str = "data/images"
    image_default_steps: int = 4

    # ── Creative — Music Generation (Lyra) ────────────────────────────────
    music_output_dir: str = "data/music"
    ace_step_model: str = "ace-step/ACE-Step-v1.5"

    # ── Creative — Video Generation (Reel) ────────────────────────────────
    video_output_dir: str = "data/video"
    wan_model_id: str = "Wan-AI/Wan2.1-T2V-1.3B"
    video_default_resolution: str = "480p"

    # ── Creative — Pipeline / Assembly ────────────────────────────────────
    creative_output_dir: str = "data/creative"
    video_transition_duration: float = 1.0
    default_video_codec: str = "libx264"

    # ── L402 Lightning ───────────────────────────────────────────────────
    # HMAC secrets for macaroon signing and invoice verification.
    # Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
    # In production (TIMMY_ENV=production), these MUST be set or the app will refuse to start.
    l402_hmac_secret: str = ""
    l402_macaroon_secret: str = ""
    lightning_backend: Literal["mock", "lnd"] = "mock"

    # ── Privacy / Sovereignty ────────────────────────────────────────────
    # Disable Agno telemetry for air-gapped/sovereign deployments.
    # Default is False (telemetry disabled) to align with sovereign AI vision.
    telemetry_enabled: bool = False

    # CORS allowed origins for the web chat interface (GitHub Pages, etc.)
    # Set CORS_ORIGINS as a comma-separated list, e.g. "http://localhost:3000,https://example.com"
    cors_origins: list[str] = ["*"]

    # Environment mode: development | production
    # In production, security settings are strictly enforced.
    timmy_env: Literal["development", "production"] = "development"

    # ── Self-Modification ──────────────────────────────────────────────
    # Enable self-modification capabilities. When enabled, the agent can
    # edit its own source code, run tests, and commit changes.
    self_modify_enabled: bool = False
    self_modify_max_retries: int = 2
    self_modify_allowed_dirs: str = "src,tests"
    self_modify_backend: str = "auto"  # "ollama", "anthropic", or "auto"

    # ── Work Orders ──────────────────────────────────────────────────
    # External users and agents can submit work orders for improvements.
    work_orders_enabled: bool = True
    work_orders_auto_execute: bool = False  # Master switch for auto-execution
    work_orders_auto_threshold: str = (
        "low"  # Max priority that auto-executes: "low" | "medium" | "high" | "none"
    )

    # ── Custom Weights & Models ──────────────────────────────────────
    # Directory for custom model weights (GGUF, safetensors, HF checkpoints).
    # Models placed here can be registered at runtime and assigned to agents.
    custom_weights_dir: str = "data/models"
    # Enable the reward model for scoring agent outputs (PRM-style).
    reward_model_enabled: bool = False
    # Reward model name (must be available via Ollama or a custom weight path).
    reward_model_name: str = ""
    # Minimum votes for majority-vote reward scoring (odd number recommended).
    reward_model_votes: int = 3

    # ── Browser Local Models (iPhone / WebGPU) ───────────────────────
    # Enable in-browser LLM inference via WebLLM for offline iPhone use.
    # When enabled, the mobile dashboard loads a small model directly
    # in the browser — no server or Ollama required.
    browser_model_enabled: bool = True
    # WebLLM model ID — must be a pre-compiled MLC model.
    # Recommended for iPhone: SmolLM2-360M (fast) or Qwen3-0.6B (smart).
    browser_model_id: str = "SmolLM2-360M-Instruct-q4f16_1-MLC"
    # Fallback to server when browser model is unavailable or too slow.
    browser_model_fallback: bool = True

    # ── Default Thinking ──────────────────────────────────────────────
    # When enabled, the agent starts an internal thought loop on server start.
    thinking_enabled: bool = True
    thinking_interval_seconds: int = 300  # 5 minutes between thoughts

    # ── OpenFang — vendored agent runtime ─────────────────────────────
    # URL where the OpenFang sidecar listens.  Set to the Docker service
    # name when running in compose, or localhost for bare-metal dev.
    openfang_url: str = "http://localhost:8080"
    # Enable/disable OpenFang integration.  When disabled, the tool
    # executor falls back to Timmy's native (simulated) execution.
    openfang_enabled: bool = False
    # Timeout in seconds for OpenFang hand execution (some hands are slow).
    openfang_timeout: int = 120

    # ── Error Logging ─────────────────────────────────────────────────
    error_log_enabled: bool = True
    error_log_dir: str = "logs"
    error_log_max_bytes: int = 5_242_880  # 5 MB
    error_log_backup_count: int = 5
    error_feedback_enabled: bool = True  # Auto-create bug report tasks
    error_dedup_window_seconds: int = 300  # 5-min dedup window

    # ── Scripture / Biblical Integration ──────────────────────────────
    # Enable the biblical text module.
    scripture_enabled: bool = True
    # Primary translation for retrieval and citation.
    scripture_translation: str = "ESV"
    # Meditation mode: sequential | thematic | lectionary
    scripture_meditation_mode: str = "sequential"
    # Background meditation interval in seconds (0 = disabled).
    scripture_meditation_interval: int = 0

    def _compute_repo_root(self) -> str:
        """Auto-detect repo root if not set."""
        if self.repo_root:
            return self.repo_root
        # Walk up from this file to find .git
        import os

        path = os.path.dirname(os.path.abspath(__file__))
        path = os.path.dirname(os.path.dirname(path))  # src/ -> project root
        while path != os.path.dirname(path):
            if os.path.exists(os.path.join(path, ".git")):
                return path
            path = os.path.dirname(path)
        return os.getcwd()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
# Ensure repo_root is computed if not set
if not settings.repo_root:
    settings.repo_root = settings._compute_repo_root()

# ── Model fallback configuration ────────────────────────────────────────────
# Primary model for reliable tool calling (llama3.1:8b-instruct)
# Fallback if primary not available: qwen2.5:14b
OLLAMA_MODEL_PRIMARY: str = "llama3.1:8b-instruct"
OLLAMA_MODEL_FALLBACK: str = "qwen2.5:14b"


def check_ollama_model_available(model_name: str) -> bool:
    """Check if a specific Ollama model is available locally."""
    try:
        import json
        import urllib.request

        url = settings.ollama_url.replace("localhost", "127.0.0.1")
        req = urllib.request.Request(
            f"{url}/api/tags",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(
                model_name == m or model_name == m.split(":")[0] or m.startswith(model_name)
                for m in models
            )
    except Exception:
        return False


def get_effective_ollama_model() -> str:
    """Get the effective Ollama model, with fallback logic."""
    # If user has overridden, use their setting
    user_model = settings.ollama_model

    # Check if user's model is available
    if check_ollama_model_available(user_model):
        return user_model

    # Try primary
    if check_ollama_model_available(OLLAMA_MODEL_PRIMARY):
        _startup_logger.warning(
            f"Requested model '{user_model}' not available. "
            f"Using primary: {OLLAMA_MODEL_PRIMARY}"
        )
        return OLLAMA_MODEL_PRIMARY

    # Try fallback
    if check_ollama_model_available(OLLAMA_MODEL_FALLBACK):
        _startup_logger.warning(
            f"Primary model '{OLLAMA_MODEL_PRIMARY}' not available. "
            f"Using fallback: {OLLAMA_MODEL_FALLBACK}"
        )
        return OLLAMA_MODEL_FALLBACK

    # Last resort - return user's setting and hope for the best
    return user_model


# ── Startup validation ───────────────────────────────────────────────────────
# Enforce security requirements — fail fast in production.
import logging as _logging
import sys

_startup_logger = _logging.getLogger("config")

# Production mode: require secrets to be set
if settings.timmy_env == "production":
    _missing = []
    if not settings.l402_hmac_secret:
        _missing.append("L402_HMAC_SECRET")
    if not settings.l402_macaroon_secret:
        _missing.append("L402_MACAROON_SECRET")
    if _missing:
        _startup_logger.error(
            "PRODUCTION SECURITY ERROR: The following secrets must be set: %s\n"
            'Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"\n'
            "Set in .env file or environment variables.",
            ", ".join(_missing),
        )
        sys.exit(1)
    _startup_logger.info("Production mode: security secrets validated ✓")
else:
    # Development mode: warn but continue
    if not settings.l402_hmac_secret:
        _startup_logger.warning(
            "SEC: L402_HMAC_SECRET is not set — "
            "set a unique secret in .env before deploying to production."
        )
    if not settings.l402_macaroon_secret:
        _startup_logger.warning(
            "SEC: L402_MACAROON_SECRET is not set — "
            "set a unique secret in .env before deploying to production."
        )
