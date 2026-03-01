"""System introspection tools for Timmy to query his own environment.

This provides true sovereignty - Timmy introspects his environment rather than
being told about it in the system prompt.
"""

import logging
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


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

    tier1_info: dict[str, Any] = {
        "exists": tier1_exists,
        "path": str(memory_md),
        "preview": tier1_content[:200] if tier1_content else None,
    }
    if tier1_exists:
        lines = memory_md.read_text().splitlines()
        tier1_info["line_count"] = len(lines)
        tier1_info["sections"] = [
            ln.lstrip("# ").strip() for ln in lines if ln.startswith("## ")
        ]

    # Vault — scan all subdirs under memory/
    vault_root = repo_root / "memory"
    vault_info: dict[str, Any] = {
        "exists": tier2_exists,
        "path": str(vault_path),
        "file_count": len(tier2_files),
        "files": tier2_files[:10],
    }
    if vault_root.exists():
        vault_info["directories"] = [d.name for d in vault_root.iterdir() if d.is_dir()]
        vault_info["total_markdown_files"] = sum(1 for _ in vault_root.rglob("*.md"))

    # Tier 3: Semantic memory row count
    tier3_info: dict[str, Any] = {"available": False}
    try:
        import sqlite3

        sem_db = repo_root / "data" / "semantic_memory.db"
        if sem_db.exists():
            conn = sqlite3.connect(str(sem_db))
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vectors'"
            ).fetchone()
            if row and row[0]:
                count = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()
                tier3_info["available"] = True
                tier3_info["vector_count"] = count[0] if count else 0
            conn.close()
    except Exception:
        pass

    # Self-coding journal stats
    journal_info: dict[str, Any] = {"available": False}
    try:
        import sqlite3 as _sqlite3

        journal_db = repo_root / "data" / "self_coding.db"
        if journal_db.exists():
            conn = _sqlite3.connect(str(journal_db))
            conn.row_factory = _sqlite3.Row
            rows = conn.execute(
                "SELECT outcome, COUNT(*) as cnt FROM modification_journal GROUP BY outcome"
            ).fetchall()
            if rows:
                counts = {r["outcome"]: r["cnt"] for r in rows}
                total = sum(counts.values())
                journal_info = {
                    "available": True,
                    "total_attempts": total,
                    "successes": counts.get("success", 0),
                    "failures": counts.get("failure", 0),
                    "success_rate": round(counts.get("success", 0) / total, 2) if total else 0,
                }
            conn.close()
    except Exception:
        pass

    return {
        "tier1_hot_memory": tier1_info,
        "tier2_vault": vault_info,
        "tier3_semantic": tier3_info,
        "self_coding_journal": journal_info,
    }


def get_task_queue_status() -> dict[str, Any]:
    """Get current task queue status for Timmy.

    Returns:
        Dict with queue counts by status and current task info.
    """
    try:
        from swarm.task_queue.models import (
            get_counts_by_status,
            get_current_task_for_agent,
        )

        counts = get_counts_by_status()
        current = get_current_task_for_agent("timmy")

        result: dict[str, Any] = {
            "counts": counts,
            "total": sum(counts.values()),
        }

        if current:
            result["current_task"] = {
                "id": current.id,
                "title": current.title,
                "type": current.task_type,
                "started_at": current.started_at,
            }
        else:
            result["current_task"] = None

        return result
    except Exception as exc:
        logger.debug("Task queue status unavailable: %s", exc)
        return {"error": str(exc)}


def get_agent_roster() -> dict[str, Any]:
    """Get the swarm agent roster with last-seen ages.

    Returns:
        Dict with agent list and summary.
    """
    try:
        from swarm.registry import list_agents

        agents = list_agents()
        now = datetime.now(timezone.utc)
        roster = []

        for agent in agents:
            last_seen = agent.last_seen
            try:
                ts = datetime.fromisoformat(last_seen)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_seconds = int((now - ts).total_seconds())
            except Exception:
                age_seconds = -1

            roster.append({
                "id": agent.id,
                "name": agent.name,
                "status": agent.status,
                "capabilities": agent.capabilities,
                "last_seen_seconds_ago": age_seconds,
            })

        return {
            "agents": roster,
            "total": len(roster),
            "idle": sum(1 for a in roster if a["status"] == "idle"),
            "busy": sum(1 for a in roster if a["status"] == "busy"),
            "offline": sum(1 for a in roster if a["status"] == "offline"),
        }
    except Exception as exc:
        logger.debug("Agent roster unavailable: %s", exc)
        return {"error": str(exc)}


def get_live_system_status() -> dict[str, Any]:
    """Comprehensive live system status — Timmy's primary introspection tool.

    Combines system info, task queue, agent roster, and memory status
    into a single snapshot. Each subsystem degrades gracefully.

    Returns:
        Dict with system, task_queue, agents, memory, and uptime sections.
    """
    result: dict[str, Any] = {}

    # System info
    try:
        result["system"] = get_system_info()
    except Exception as exc:
        result["system"] = {"error": str(exc)}

    # Task queue
    result["task_queue"] = get_task_queue_status()

    # Agent roster
    result["agents"] = get_agent_roster()

    # Memory status
    try:
        result["memory"] = get_memory_status()
    except Exception as exc:
        result["memory"] = {"error": str(exc)}

    # Uptime
    try:
        from dashboard.routes.health import _START_TIME

        uptime = (datetime.now(timezone.utc) - _START_TIME).total_seconds()
        result["uptime_seconds"] = int(uptime)
    except Exception:
        result["uptime_seconds"] = None

    # Discord status
    try:
        from integrations.chat_bridge.vendors.discord import discord_bot

        result["discord"] = {"state": discord_bot.state.name}
    except Exception:
        result["discord"] = {"state": "unknown"}

    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    return result
