from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Ollama host — override with OLLAMA_URL env var or .env file
    ollama_url: str = "http://localhost:11434"

    # LLM model passed to Agno/Ollama — override with OLLAMA_MODEL
    ollama_model: str = "llama3.2"

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
    # MUST be changed from defaults before deploying to production.
    # Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
    l402_hmac_secret: str = "timmy-hmac-secret"
    l402_macaroon_secret: str = "timmy-macaroon-secret"
    lightning_backend: Literal["mock", "lnd"] = "mock"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# ── Startup validation ───────────────────────────────────────────────────────
# Warn when security-sensitive settings are using defaults.
import logging as _logging

_startup_logger = _logging.getLogger("config")

if settings.l402_hmac_secret == "timmy-hmac-secret":
    _startup_logger.warning(
        "SEC: L402_HMAC_SECRET is using the default value — "
        "set a unique secret in .env before deploying to production."
    )
if settings.l402_macaroon_secret == "timmy-macaroon-secret":
    _startup_logger.warning(
        "SEC: L402_MACAROON_SECRET is using the default value — "
        "set a unique secret in .env before deploying to production."
    )
