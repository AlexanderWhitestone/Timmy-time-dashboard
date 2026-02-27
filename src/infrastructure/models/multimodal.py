"""Multi-modal model support with automatic capability detection and fallbacks.

Provides:
  - Model capability detection (vision, audio, etc.)
  - Automatic model pulling with fallback chains
  - Content-type aware model selection
  - Graceful degradation when primary models unavailable

No cloud by default — tries local first, falls back through configured options.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


class ModelCapability(Enum):
    """Capabilities a model can have."""
    TEXT = auto()      # Standard text completion
    VISION = auto()    # Image understanding
    AUDIO = auto()     # Audio/speech processing
    TOOLS = auto()     # Function calling / tool use
    JSON = auto()      # Structured output / JSON mode
    STREAMING = auto() # Streaming responses


# Known model capabilities (local Ollama models)
# These are used when we can't query the model directly
KNOWN_MODEL_CAPABILITIES: dict[str, set[ModelCapability]] = {
    # Llama 3.x series
    "llama3.1": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "llama3.1:8b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "llama3.1:8b-instruct": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "llama3.1:70b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "llama3.1:405b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "llama3.2": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING, ModelCapability.VISION},
    "llama3.2:1b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "llama3.2:3b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING, ModelCapability.VISION},
    "llama3.2-vision": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING, ModelCapability.VISION},
    "llama3.2-vision:11b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING, ModelCapability.VISION},
    
    # Qwen series
    "qwen2.5": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "qwen2.5:7b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "qwen2.5:14b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "qwen2.5:32b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "qwen2.5:72b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "qwen2.5-vl": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING, ModelCapability.VISION},
    "qwen2.5-vl:3b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING, ModelCapability.VISION},
    "qwen2.5-vl:7b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING, ModelCapability.VISION},
    
    # DeepSeek series
    "deepseek-r1": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "deepseek-r1:1.5b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "deepseek-r1:7b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "deepseek-r1:14b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "deepseek-r1:32b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "deepseek-r1:70b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "deepseek-v3": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    
    # Gemma series
    "gemma2": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "gemma2:2b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "gemma2:9b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "gemma2:27b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    
    # Mistral series
    "mistral": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "mistral:7b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "mistral-nemo": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "mistral-small": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "mistral-large": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    
    # Vision-specific models
    "llava": {ModelCapability.TEXT, ModelCapability.VISION, ModelCapability.STREAMING},
    "llava:7b": {ModelCapability.TEXT, ModelCapability.VISION, ModelCapability.STREAMING},
    "llava:13b": {ModelCapability.TEXT, ModelCapability.VISION, ModelCapability.STREAMING},
    "llava:34b": {ModelCapability.TEXT, ModelCapability.VISION, ModelCapability.STREAMING},
    "llava-phi3": {ModelCapability.TEXT, ModelCapability.VISION, ModelCapability.STREAMING},
    "llava-llama3": {ModelCapability.TEXT, ModelCapability.VISION, ModelCapability.STREAMING},
    "bakllava": {ModelCapability.TEXT, ModelCapability.VISION, ModelCapability.STREAMING},
    "moondream": {ModelCapability.TEXT, ModelCapability.VISION, ModelCapability.STREAMING},
    "moondream:1.8b": {ModelCapability.TEXT, ModelCapability.VISION, ModelCapability.STREAMING},
    
    # Phi series
    "phi3": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "phi3:3.8b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "phi3:14b": {ModelCapability.TEXT, ModelCapability.JSON, ModelCapability.STREAMING},
    "phi4": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    
    # Command R
    "command-r": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "command-r:35b": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "command-r-plus": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    
    # Granite (IBM)
    "granite3-dense": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
    "granite3-moe": {ModelCapability.TEXT, ModelCapability.TOOLS, ModelCapability.JSON, ModelCapability.STREAMING},
}


# Default fallback chains for each capability
# These are tried in order when the primary model doesn't support a capability
DEFAULT_FALLBACK_CHAINS: dict[ModelCapability, list[str]] = {
    ModelCapability.VISION: [
        "llama3.2:3b",           # Fast vision model
        "llava:7b",              # Classic vision model
        "qwen2.5-vl:3b",         # Qwen vision
        "moondream:1.8b",        # Tiny vision model (last resort)
    ],
    ModelCapability.TOOLS: [
        "llama3.1:8b-instruct",  # Best tool use
        "llama3.2:3b",           # Smaller but capable
        "qwen2.5:7b",            # Reliable fallback
    ],
    ModelCapability.AUDIO: [
        # Audio models are less common in Ollama
        # Would need specific audio-capable models here
    ],
}


@dataclass
class ModelInfo:
    """Information about a model's capabilities and availability."""
    name: str
    capabilities: set[ModelCapability] = field(default_factory=set)
    is_available: bool = False
    is_pulled: bool = False
    size_mb: Optional[int] = None
    description: str = ""
    
    def supports(self, capability: ModelCapability) -> bool:
        """Check if model supports a specific capability."""
        return capability in self.capabilities


class MultiModalManager:
    """Manages multi-modal model capabilities and fallback chains.
    
    This class:
    1. Detects what capabilities each model has
    2. Maintains fallback chains for different capabilities
    3. Pulls models on-demand with automatic fallback
    4. Routes requests to appropriate models based on content type
    """
    
    def __init__(self, ollama_url: Optional[str] = None) -> None:
        self.ollama_url = ollama_url or settings.ollama_url
        self._available_models: dict[str, ModelInfo] = {}
        self._fallback_chains: dict[ModelCapability, list[str]] = dict(DEFAULT_FALLBACK_CHAINS)
        self._refresh_available_models()
    
    def _refresh_available_models(self) -> None:
        """Query Ollama for available models."""
        try:
            import urllib.request
            import json
            
            url = self.ollama_url.replace("localhost", "127.0.0.1")
            req = urllib.request.Request(
                f"{url}/api/tags",
                method="GET",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                
                for model_data in data.get("models", []):
                    name = model_data.get("name", "")
                    self._available_models[name] = ModelInfo(
                        name=name,
                        capabilities=self._detect_capabilities(name),
                        is_available=True,
                        is_pulled=True,
                        size_mb=model_data.get("size", 0) // (1024 * 1024),
                        description=model_data.get("details", {}).get("family", ""),
                    )
                    
            logger.info("Found %d models in Ollama", len(self._available_models))
            
        except Exception as exc:
            logger.warning("Could not refresh available models: %s", exc)
    
    def _detect_capabilities(self, model_name: str) -> set[ModelCapability]:
        """Detect capabilities for a model based on known data."""
        # Normalize model name (strip tags for lookup)
        base_name = model_name.split(":")[0]
        
        # Try exact match first
        if model_name in KNOWN_MODEL_CAPABILITIES:
            return set(KNOWN_MODEL_CAPABILITIES[model_name])
        
        # Try base name match
        if base_name in KNOWN_MODEL_CAPABILITIES:
            return set(KNOWN_MODEL_CAPABILITIES[base_name])
        
        # Default to text-only for unknown models
        logger.debug("Unknown model %s, defaulting to TEXT only", model_name)
        return {ModelCapability.TEXT, ModelCapability.STREAMING}
    
    def get_model_capabilities(self, model_name: str) -> set[ModelCapability]:
        """Get capabilities for a specific model."""
        if model_name in self._available_models:
            return self._available_models[model_name].capabilities
        return self._detect_capabilities(model_name)
    
    def model_supports(self, model_name: str, capability: ModelCapability) -> bool:
        """Check if a model supports a specific capability."""
        capabilities = self.get_model_capabilities(model_name)
        return capability in capabilities
    
    def get_models_with_capability(self, capability: ModelCapability) -> list[ModelInfo]:
        """Get all available models that support a capability."""
        return [
            info for info in self._available_models.values()
            if capability in info.capabilities
        ]
    
    def get_best_model_for(
        self, 
        capability: ModelCapability,
        preferred_model: Optional[str] = None
    ) -> Optional[str]:
        """Get the best available model for a specific capability.
        
        Args:
            capability: The required capability
            preferred_model: Preferred model to use if available and capable
            
        Returns:
            Model name or None if no suitable model found
        """
        # Check if preferred model supports this capability
        if preferred_model:
            if preferred_model in self._available_models:
                if self.model_supports(preferred_model, capability):
                    return preferred_model
                logger.debug(
                    "Preferred model %s doesn't support %s, checking fallbacks",
                    preferred_model, capability.name
                )
        
        # Check fallback chain for this capability
        fallback_chain = self._fallback_chains.get(capability, [])
        for model_name in fallback_chain:
            if model_name in self._available_models:
                logger.debug("Using fallback model %s for %s", model_name, capability.name)
                return model_name
        
        # Find any available model with this capability
        capable_models = self.get_models_with_capability(capability)
        if capable_models:
            # Sort by size (prefer smaller/faster models as fallback)
            capable_models.sort(key=lambda m: m.size_mb or float('inf'))
            return capable_models[0].name
        
        return None
    
    def pull_model_with_fallback(
        self,
        primary_model: str,
        capability: Optional[ModelCapability] = None,
        auto_pull: bool = True,
    ) -> tuple[str, bool]:
        """Pull a model with automatic fallback if unavailable.
        
        Args:
            primary_model: The desired model to use
            capability: Required capability (for finding fallback)
            auto_pull: Whether to attempt pulling missing models
            
        Returns:
            Tuple of (model_name, is_fallback)
        """
        # Check if primary model is already available
        if primary_model in self._available_models:
            return primary_model, False
        
        # Try to pull the primary model
        if auto_pull:
            if self._pull_model(primary_model):
                return primary_model, False
        
        # Need to find a fallback
        if capability:
            fallback = self.get_best_model_for(capability, primary_model)
            if fallback:
                logger.info(
                    "Primary model %s unavailable, using fallback %s",
                    primary_model, fallback
                )
                return fallback, True
        
        # Last resort: use the configured default model
        default_model = settings.ollama_model
        if default_model in self._available_models:
            logger.warning(
                "Falling back to default model %s (primary: %s unavailable)",
                default_model, primary_model
            )
            return default_model, True
        
        # Absolute last resort
        return primary_model, False
    
    def _pull_model(self, model_name: str) -> bool:
        """Attempt to pull a model from Ollama.
        
        Returns:
            True if successful or model already exists
        """
        try:
            import urllib.request
            import json
            
            logger.info("Pulling model: %s", model_name)
            
            url = self.ollama_url.replace("localhost", "127.0.0.1")
            req = urllib.request.Request(
                f"{url}/api/pull",
                method="POST",
                headers={"Content-Type": "application/json"},
                data=json.dumps({"name": model_name, "stream": False}).encode(),
            )
            
            with urllib.request.urlopen(req, timeout=300) as response:
                if response.status == 200:
                    logger.info("Successfully pulled model: %s", model_name)
                    # Refresh available models
                    self._refresh_available_models()
                    return True
                else:
                    logger.error("Failed to pull %s: HTTP %s", model_name, response.status)
                    return False
                    
        except Exception as exc:
            logger.error("Error pulling model %s: %s", model_name, exc)
            return False
    
    def configure_fallback_chain(
        self, 
        capability: ModelCapability, 
        models: list[str]
    ) -> None:
        """Configure a custom fallback chain for a capability."""
        self._fallback_chains[capability] = models
        logger.info("Configured fallback chain for %s: %s", capability.name, models)
    
    def get_fallback_chain(self, capability: ModelCapability) -> list[str]:
        """Get the fallback chain for a capability."""
        return list(self._fallback_chains.get(capability, []))
    
    def list_available_models(self) -> list[ModelInfo]:
        """List all available models with their capabilities."""
        return list(self._available_models.values())
    
    def refresh(self) -> None:
        """Refresh the list of available models."""
        self._refresh_available_models()
    
    def get_model_for_content(
        self,
        content_type: str,  # "text", "image", "audio", "multimodal"
        preferred_model: Optional[str] = None,
    ) -> tuple[str, bool]:
        """Get appropriate model based on content type.
        
        Args:
            content_type: Type of content (text, image, audio, multimodal)
            preferred_model: User's preferred model
            
        Returns:
            Tuple of (model_name, is_fallback)
        """
        content_type = content_type.lower()
        
        if content_type in ("image", "vision", "multimodal"):
            # For vision content, we need a vision-capable model
            return self.pull_model_with_fallback(
                preferred_model or "llava:7b",
                capability=ModelCapability.VISION,
            )
        
        elif content_type == "audio":
            # Audio support is limited in Ollama
            # Would need specific audio models
            logger.warning("Audio support is limited, falling back to text model")
            return self.pull_model_with_fallback(
                preferred_model or settings.ollama_model,
                capability=ModelCapability.TEXT,
            )
        
        else:
            # Standard text content
            return self.pull_model_with_fallback(
                preferred_model or settings.ollama_model,
                capability=ModelCapability.TEXT,
            )


# Module-level singleton
_multimodal_manager: Optional[MultiModalManager] = None


def get_multimodal_manager() -> MultiModalManager:
    """Get or create the multi-modal manager singleton."""
    global _multimodal_manager
    if _multimodal_manager is None:
        _multimodal_manager = MultiModalManager()
    return _multimodal_manager


def get_model_for_capability(
    capability: ModelCapability,
    preferred_model: Optional[str] = None
) -> Optional[str]:
    """Convenience function to get best model for a capability."""
    return get_multimodal_manager().get_best_model_for(capability, preferred_model)


def pull_model_with_fallback(
    primary_model: str,
    capability: Optional[ModelCapability] = None,
    auto_pull: bool = True,
) -> tuple[str, bool]:
    """Convenience function to pull model with fallback."""
    return get_multimodal_manager().pull_model_with_fallback(
        primary_model, capability, auto_pull
    )


def model_supports_vision(model_name: str) -> bool:
    """Check if a model supports vision."""
    return get_multimodal_manager().model_supports(model_name, ModelCapability.VISION)


def model_supports_tools(model_name: str) -> bool:
    """Check if a model supports tool calling."""
    return get_multimodal_manager().model_supports(model_name, ModelCapability.TOOLS)
