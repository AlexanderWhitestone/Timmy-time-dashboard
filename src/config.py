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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
