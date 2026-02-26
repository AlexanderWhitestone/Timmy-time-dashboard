from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    # ── AirLLM / backend selection ───────────────────────────────────────────
    # "ollama"  — always use Ollama (default, safe everywhere)
    # "airllm"  — always use AirLLM (requires pip install ".[bigbrain]")
    # "auto"    — use AirLLM on Apple Silicon if airllm is installed,
    #             fall back to Ollama otherwise
    timmy_model_backend: Literal["ollama", "airllm", "auto"] = "ollama"

    # AirLLM model size when backend is airllm or auto.
    # Larger = smarter, but needs more RAM / disk.
    # 8b  ~16 GB  |  70b  ~140 GB  |  405b  ~810 GB
    airllm_model_size: Literal["8b", "70b", "405b"] = "70b"

    # ── Spark Intelligence ────────────────────────────────────────────────
    # Enable/disable the Spark cognitive layer.
    # When enabled, Spark captures swarm events, runs EIDOS predictions,
    # consolidates memories, and generates advisory recommendations.
    spark_enabled: bool = True

    # ── Git / DevOps ──────────────────────────────────────────────────────
    git_default_repo_dir: str = "~/repos"

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

    # Environment mode: development | production
    # In production, security settings are strictly enforced.
    timmy_env: Literal["development", "production"] = "development"

    # ── Self-Modification ──────────────────────────────────────────────
    # Enable self-modification capabilities. When enabled, Timmy can
    # edit its own source code, run tests, and commit changes.
    self_modify_enabled: bool = False
    self_modify_max_retries: int = 2
    self_modify_allowed_dirs: str = "src,tests"
    self_modify_backend: str = "auto"  # "ollama", "anthropic", or "auto"

    # ── Work Orders ──────────────────────────────────────────────────
    # External users and agents can submit work orders for improvements.
    work_orders_enabled: bool = True
    work_orders_auto_execute: bool = False  # Master switch for auto-execution
    work_orders_auto_threshold: str = "low"  # Max priority that auto-executes: "low" | "medium" | "high" | "none"

    # ── Scripture / Biblical Integration ──────────────────────────────
    # Enable the sovereign biblical text module.  When enabled, Timmy
    # loads the local ESV text corpus and runs meditation workflows.
    scripture_enabled: bool = True
    # Primary translation for retrieval and citation.
    scripture_translation: str = "ESV"
    # Meditation mode: sequential | thematic | lectionary
    scripture_meditation_mode: str = "sequential"
    # Background meditation interval in seconds (0 = disabled).
    scripture_meditation_interval: int = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# ── Model fallback configuration ────────────────────────────────────────────
# Primary model for reliable tool calling (llama3.1:8b-instruct)
# Fallback if primary not available: qwen2.5:14b
OLLAMA_MODEL_PRIMARY: str = "llama3.1:8b-instruct"
OLLAMA_MODEL_FALLBACK: str = "qwen2.5:14b"


def check_ollama_model_available(model_name: str) -> bool:
    """Check if a specific Ollama model is available locally."""
    try:
        import urllib.request
        url = settings.ollama_url.replace("localhost", "127.0.0.1")
        req = urllib.request.Request(
            f"{url}/api/tags",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            import json
            data = json.loads(response.read().decode())
            models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
            # Check for exact match or model name without tag
            return any(model_name in m or m in model_name for m in models)
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
            "Generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\"\n"
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
