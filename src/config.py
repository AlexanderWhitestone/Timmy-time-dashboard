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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
