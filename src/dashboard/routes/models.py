"""Custom model management routes — register, list, assign, and swap models.

Provides a REST API for managing custom model weights and their assignment
to swarm agents.  Inspired by OpenClaw-RL's multi-model orchestration.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import settings
from infrastructure.models.registry import (
    CustomModel,
    ModelFormat,
    ModelRegistry,
    ModelRole,
    model_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["models"])
api_router = APIRouter(prefix="/api/v1/models", tags=["models-api"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class RegisterModelRequest(BaseModel):
    """Request body for model registration."""
    name: str
    format: str  # gguf, safetensors, hf, ollama
    path: str
    role: str = "general"
    context_window: int = 4096
    description: str = ""
    default_temperature: float = 0.7
    max_tokens: int = 2048


class AssignModelRequest(BaseModel):
    """Request body for assigning a model to an agent."""
    agent_id: str
    model_name: str


class SetActiveRequest(BaseModel):
    """Request body for enabling/disabling a model."""
    active: bool


# ── API endpoints ─────────────────────────────────────────────────────────────


@api_router.get("")
async def list_models(role: Optional[str] = None) -> dict[str, Any]:
    """List all registered custom models."""
    model_role = ModelRole(role) if role else None
    models = model_registry.list_models(role=model_role)
    return {
        "models": [
            {
                "name": m.name,
                "format": m.format.value,
                "path": m.path,
                "role": m.role.value,
                "context_window": m.context_window,
                "description": m.description,
                "active": m.active,
                "registered_at": m.registered_at,
                "default_temperature": m.default_temperature,
                "max_tokens": m.max_tokens,
            }
            for m in models
        ],
        "total": len(models),
        "weights_dir": settings.custom_weights_dir,
    }


@api_router.post("")
async def register_model(request: RegisterModelRequest) -> dict[str, Any]:
    """Register a new custom model."""
    try:
        fmt = ModelFormat(request.format)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format: {request.format}. "
                   f"Choose from: {[f.value for f in ModelFormat]}",
        )
    try:
        role = ModelRole(request.role)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role: {request.role}. "
                   f"Choose from: {[r.value for r in ModelRole]}",
        )

    # Validate path exists for non-Ollama formats
    if fmt != ModelFormat.OLLAMA:
        weight_path = Path(request.path)
        if not weight_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Weight path does not exist: {request.path}",
            )

    model = CustomModel(
        name=request.name,
        format=fmt,
        path=request.path,
        role=role,
        context_window=request.context_window,
        description=request.description,
        default_temperature=request.default_temperature,
        max_tokens=request.max_tokens,
    )
    registered = model_registry.register(model)
    return {
        "message": f"Model {registered.name} registered",
        "model": {
            "name": registered.name,
            "format": registered.format.value,
            "role": registered.role.value,
            "path": registered.path,
        },
    }


@api_router.get("/{model_name}")
async def get_model(model_name: str) -> dict[str, Any]:
    """Get details of a specific model."""
    model = model_registry.get(model_name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
    return {
        "name": model.name,
        "format": model.format.value,
        "path": model.path,
        "role": model.role.value,
        "context_window": model.context_window,
        "description": model.description,
        "active": model.active,
        "registered_at": model.registered_at,
        "default_temperature": model.default_temperature,
        "max_tokens": model.max_tokens,
    }


@api_router.delete("/{model_name}")
async def unregister_model(model_name: str) -> dict[str, str]:
    """Remove a model from the registry."""
    if not model_registry.unregister(model_name):
        raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
    return {"message": f"Model {model_name} unregistered"}


@api_router.patch("/{model_name}/active")
async def set_model_active(
    model_name: str, request: SetActiveRequest
) -> dict[str, str]:
    """Enable or disable a model."""
    if not model_registry.set_active(model_name, request.active):
        raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
    state = "enabled" if request.active else "disabled"
    return {"message": f"Model {model_name} {state}"}


# ── Agent assignment endpoints ────────────────────────────────────────────────


@api_router.get("/assignments/all")
async def list_assignments() -> dict[str, Any]:
    """List all agent-to-model assignments."""
    assignments = model_registry.get_agent_assignments()
    return {
        "assignments": [
            {"agent_id": aid, "model_name": mname}
            for aid, mname in assignments.items()
        ],
        "total": len(assignments),
    }


@api_router.post("/assignments")
async def assign_model(request: AssignModelRequest) -> dict[str, str]:
    """Assign a model to a swarm agent."""
    if not model_registry.assign_model(request.agent_id, request.model_name):
        raise HTTPException(
            status_code=404,
            detail=f"Model {request.model_name} not found in registry",
        )
    return {
        "message": f"Model {request.model_name} assigned to {request.agent_id}",
    }


@api_router.delete("/assignments/{agent_id}")
async def unassign_model(agent_id: str) -> dict[str, str]:
    """Remove model assignment from an agent (reverts to default)."""
    if not model_registry.unassign_model(agent_id):
        raise HTTPException(
            status_code=404,
            detail=f"No model assignment for agent {agent_id}",
        )
    return {"message": f"Model assignment removed for {agent_id}"}


# ── Role-based lookups ────────────────────────────────────────────────────────


@api_router.get("/roles/reward")
async def get_reward_model() -> dict[str, Any]:
    """Get the active reward (PRM) model."""
    model = model_registry.get_reward_model()
    if not model:
        return {"reward_model": None, "reward_enabled": settings.reward_model_enabled}
    return {
        "reward_model": {
            "name": model.name,
            "format": model.format.value,
            "path": model.path,
        },
        "reward_enabled": settings.reward_model_enabled,
    }


@api_router.get("/roles/teacher")
async def get_teacher_model() -> dict[str, Any]:
    """Get the active teacher model for distillation."""
    model = model_registry.get_teacher_model()
    if not model:
        return {"teacher_model": None}
    return {
        "teacher_model": {
            "name": model.name,
            "format": model.format.value,
            "path": model.path,
        },
    }


# ── Dashboard page ────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def models_page(request: Request):
    """Custom models management dashboard page."""
    models = model_registry.list_models()
    assignments = model_registry.get_agent_assignments()
    reward = model_registry.get_reward_model()

    return templates.TemplateResponse(
        request,
        "models.html",
        {
            "page_title": "Custom Models",
            "models": models,
            "assignments": assignments,
            "reward_model": reward,
            "weights_dir": settings.custom_weights_dir,
            "reward_enabled": settings.reward_model_enabled,
        },
    )
