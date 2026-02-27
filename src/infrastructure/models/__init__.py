"""Infrastructure models package."""

from infrastructure.models.registry import (
    CustomModel,
    ModelFormat,
    ModelRegistry,
    ModelRole,
    model_registry,
)
from infrastructure.models.multimodal import (
    ModelCapability,
    ModelInfo,
    MultiModalManager,
    get_model_for_capability,
    get_multimodal_manager,
    model_supports_tools,
    model_supports_vision,
    pull_model_with_fallback,
)

__all__ = [
    # Registry
    "CustomModel",
    "ModelFormat",
    "ModelRegistry",
    "ModelRole",
    "model_registry",
    # Multi-modal
    "ModelCapability",
    "ModelInfo",
    "MultiModalManager",
    "get_model_for_capability",
    "get_multimodal_manager",
    "model_supports_tools",
    "model_supports_vision",
    "pull_model_with_fallback",
]
