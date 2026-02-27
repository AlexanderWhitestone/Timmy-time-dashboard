"""Custom model registry — register, load, and manage model weights.

Tracks custom models (GGUF files, HF checkpoints, Ollama modelfiles)
and their assignment to swarm agents.  Models can be registered at
runtime via the API or pre-configured via providers.yaml.

Inspired by OpenClaw-RL's multi-model orchestration where distinct
model roles (student, teacher, judge/PRM) run on dedicated resources.
"""

import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

DB_PATH = Path("data/swarm.db")


class ModelFormat(str, Enum):
    """Supported model weight formats."""
    GGUF = "gguf"               # Ollama-compatible quantised weights
    SAFETENSORS = "safetensors" # HuggingFace safetensors
    HF_CHECKPOINT = "hf"        # Full HuggingFace checkpoint directory
    OLLAMA = "ollama"           # Already loaded in Ollama by name


class ModelRole(str, Enum):
    """Role a model can play in the system (OpenClaw-RL style)."""
    GENERAL = "general"     # Default agent inference
    REWARD = "reward"       # Process Reward Model (PRM) scoring
    TEACHER = "teacher"     # On-policy distillation teacher
    JUDGE = "judge"         # Output quality evaluation


@dataclass
class CustomModel:
    """A registered custom model."""
    name: str
    format: ModelFormat
    path: str                       # Absolute path or Ollama model name
    role: ModelRole = ModelRole.GENERAL
    context_window: int = 4096
    description: str = ""
    registered_at: str = ""
    active: bool = True
    # Per-model generation settings
    default_temperature: float = 0.7
    max_tokens: int = 2048

    def __post_init__(self):
        if not self.registered_at:
            self.registered_at = datetime.now(timezone.utc).isoformat()


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_models (
            name            TEXT PRIMARY KEY,
            format          TEXT NOT NULL,
            path            TEXT NOT NULL,
            role            TEXT NOT NULL DEFAULT 'general',
            context_window  INTEGER NOT NULL DEFAULT 4096,
            description     TEXT NOT NULL DEFAULT '',
            registered_at   TEXT NOT NULL,
            active          INTEGER NOT NULL DEFAULT 1,
            default_temperature REAL NOT NULL DEFAULT 0.7,
            max_tokens      INTEGER NOT NULL DEFAULT 2048
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_model_assignments (
            agent_id    TEXT PRIMARY KEY,
            model_name  TEXT NOT NULL,
            assigned_at TEXT NOT NULL,
            FOREIGN KEY (model_name) REFERENCES custom_models(name)
        )
        """
    )
    conn.commit()
    return conn


class ModelRegistry:
    """Singleton registry for custom models and agent-model assignments."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # In-memory cache for fast lookups
        self._models: dict[str, CustomModel] = {}
        self._agent_assignments: dict[str, str] = {}
        self._load_from_db()

    def _load_from_db(self) -> None:
        """Bootstrap cache from SQLite."""
        try:
            conn = _get_conn()
            for row in conn.execute("SELECT * FROM custom_models WHERE active = 1").fetchall():
                self._models[row["name"]] = CustomModel(
                    name=row["name"],
                    format=ModelFormat(row["format"]),
                    path=row["path"],
                    role=ModelRole(row["role"]),
                    context_window=row["context_window"],
                    description=row["description"],
                    registered_at=row["registered_at"],
                    active=bool(row["active"]),
                    default_temperature=row["default_temperature"],
                    max_tokens=row["max_tokens"],
                )
            for row in conn.execute("SELECT * FROM agent_model_assignments").fetchall():
                self._agent_assignments[row["agent_id"]] = row["model_name"]
            conn.close()
        except Exception as exc:
            logger.warning("Failed to load model registry from DB: %s", exc)

    # ── Model CRUD ─────────────────────────────────────────────────────────

    def register(self, model: CustomModel) -> CustomModel:
        """Register a new custom model."""
        with self._lock:
            conn = _get_conn()
            conn.execute(
                """
                INSERT OR REPLACE INTO custom_models
                    (name, format, path, role, context_window, description,
                     registered_at, active, default_temperature, max_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model.name, model.format.value, model.path,
                    model.role.value, model.context_window, model.description,
                    model.registered_at, int(model.active),
                    model.default_temperature, model.max_tokens,
                ),
            )
            conn.commit()
            conn.close()
            self._models[model.name] = model
            logger.info("Registered model: %s (%s)", model.name, model.format.value)
            return model

    def unregister(self, name: str) -> bool:
        """Remove a model from the registry."""
        with self._lock:
            if name not in self._models:
                return False
            conn = _get_conn()
            conn.execute("DELETE FROM custom_models WHERE name = ?", (name,))
            conn.execute(
                "DELETE FROM agent_model_assignments WHERE model_name = ?", (name,)
            )
            conn.commit()
            conn.close()
            del self._models[name]
            # Remove any agent assignments using this model
            self._agent_assignments = {
                k: v for k, v in self._agent_assignments.items() if v != name
            }
            logger.info("Unregistered model: %s", name)
            return True

    def get(self, name: str) -> Optional[CustomModel]:
        """Look up a model by name."""
        return self._models.get(name)

    def list_models(self, role: Optional[ModelRole] = None) -> list[CustomModel]:
        """List all registered models, optionally filtered by role."""
        models = list(self._models.values())
        if role is not None:
            models = [m for m in models if m.role == role]
        return models

    def set_active(self, name: str, active: bool) -> bool:
        """Enable or disable a model without removing it."""
        model = self._models.get(name)
        if not model:
            return False
        with self._lock:
            model.active = active
            conn = _get_conn()
            conn.execute(
                "UPDATE custom_models SET active = ? WHERE name = ?",
                (int(active), name),
            )
            conn.commit()
            conn.close()
        return True

    # ── Agent-model assignments ────────────────────────────────────────────

    def assign_model(self, agent_id: str, model_name: str) -> bool:
        """Assign a specific model to an agent."""
        if model_name not in self._models:
            return False
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            conn = _get_conn()
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_model_assignments
                    (agent_id, model_name, assigned_at)
                VALUES (?, ?, ?)
                """,
                (agent_id, model_name, now),
            )
            conn.commit()
            conn.close()
            self._agent_assignments[agent_id] = model_name
            logger.info("Assigned model %s to agent %s", model_name, agent_id)
        return True

    def unassign_model(self, agent_id: str) -> bool:
        """Remove model assignment from an agent (falls back to default)."""
        with self._lock:
            if agent_id not in self._agent_assignments:
                return False
            conn = _get_conn()
            conn.execute(
                "DELETE FROM agent_model_assignments WHERE agent_id = ?",
                (agent_id,),
            )
            conn.commit()
            conn.close()
            del self._agent_assignments[agent_id]
        return True

    def get_agent_model(self, agent_id: str) -> Optional[CustomModel]:
        """Get the model assigned to an agent, or None for default."""
        model_name = self._agent_assignments.get(agent_id)
        if model_name:
            return self._models.get(model_name)
        return None

    def get_agent_assignments(self) -> dict[str, str]:
        """Return all agent-to-model assignments."""
        return dict(self._agent_assignments)

    # ── Role-based lookups ─────────────────────────────────────────────────

    def get_reward_model(self) -> Optional[CustomModel]:
        """Get the active reward/PRM model, if any."""
        reward_models = self.list_models(role=ModelRole.REWARD)
        active = [m for m in reward_models if m.active]
        return active[0] if active else None

    def get_teacher_model(self) -> Optional[CustomModel]:
        """Get the active teacher model for distillation."""
        teacher_models = self.list_models(role=ModelRole.TEACHER)
        active = [m for m in teacher_models if m.active]
        return active[0] if active else None


# Module-level singleton
model_registry = ModelRegistry()
