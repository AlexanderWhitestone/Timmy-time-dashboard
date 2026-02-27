"""System introspection tools for Timmy to query his own environment.

This provides true sovereignty - Timmy introspects his environment rather than
being told about it in the system prompt.
"""

import platform
import sys
from pathlib import Path
from typing import Any

import httpx


def get_system_info() -> dict[str, Any]:
    """Introspect the runtime environment to discover system information.

    Returns:
        Dict containing:
        - python_version: Python version
        - platform: OS platform
        - model: Current Ollama model (queried from API)
        - model_backend: Configured backend (ollama/airllm/grok)
        - ollama_url: Ollama host URL
        - repo_root: Repository root path
        - grok_enabled: Whether GROK is enabled
        - spark_enabled: Whether Spark is enabled
        - memory_vault_exists: Whether memory vault is initialized
    """
    from config import settings

    info = {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.system(),
        "model_backend": settings.timmy_model_backend,
        "ollama_url": settings.ollama_url,
        "repo_root": settings.repo_root,
        "grok_enabled": settings.grok_enabled,
        "spark_enabled": settings.spark_enabled,
    }

    # Query Ollama for current model
    model_name = _get_ollama_model()
    info["model"] = model_name

    # Check if memory vault exists
    vault_path = Path(settings.repo_root) / "memory" / "self"
    info["memory_vault_exists"] = vault_path.exists()

    return info


def _get_ollama_model() -> str:
    """Query Ollama API to get the current model."""
    from config import settings

    try:
        # First try to get tags to see available models
        response = httpx.get(f"{settings.ollama_url}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            # Check if configured model is available
            for model in models:
                if model.get("name", "").startswith(
                    settings.ollama_model.split(":")[0]
                ):
                    return settings.ollama_model

            # Fallback: return configured model
            return settings.ollama_model
    except Exception:
        pass

    # Fallback to configured model
    return settings.ollama_model


def check_ollama_health() -> dict[str, Any]:
    """Check if Ollama is accessible and healthy.

    Returns:
        Dict with status, model, and available models
    """
    from config import settings

    result = {
        "accessible": False,
        "model": settings.ollama_model,
        "available_models": [],
        "error": None,
    }

    try:
        # Check tags endpoint
        response = httpx.get(f"{settings.ollama_url}/api/tags", timeout=5)
        if response.status_code == 200:
            result["accessible"] = True
            models = response.json().get("models", [])
            result["available_models"] = [m.get("name", "") for m in models]
    except Exception as e:
        result["error"] = str(e)

    return result


def get_memory_status() -> dict[str, Any]:
    """Get the status of Timmy's memory system.

    Returns:
        Dict with memory tier information
    """
    from config import settings

    repo_root = Path(settings.repo_root)

    # Check tier 1: Hot memory
    memory_md = repo_root / "MEMORY.md"
    tier1_exists = memory_md.exists()
    tier1_content = ""
    if tier1_exists:
        tier1_content = memory_md.read_text()[:500]  # First 500 chars

    # Check tier 2: Vault
    vault_path = repo_root / "memory" / "self"
    tier2_exists = vault_path.exists()
    tier2_files = []
    if tier2_exists:
        tier2_files = [f.name for f in vault_path.iterdir() if f.is_file()]

    return {
        "tier1_hot_memory": {
            "exists": tier1_exists,
            "path": str(memory_md),
            "preview": tier1_content[:200] if tier1_content else None,
        },
        "tier2_vault": {
            "exists": tier2_exists,
            "path": str(vault_path),
            "file_count": len(tier2_files),
            "files": tier2_files[:10],  # First 10 files
        },
    }
