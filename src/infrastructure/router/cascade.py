"""Cascade LLM Router — Automatic failover between providers.

Routes requests through an ordered list of LLM providers,
automatically failing over on rate limits or errors.
Tracks metrics for latency, errors, and cost.

Now with multi-modal support — automatically selects vision-capable
models for image inputs and falls back through capability chains.
"""

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

try:
    import requests
except ImportError:
    requests = None  # type: ignore

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    """Health status of a provider."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Working but slow or occasional errors
    UNHEALTHY = "unhealthy"  # Circuit breaker open
    DISABLED = "disabled"


class CircuitState(Enum):
    """Circuit breaker state."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if recovered


class ContentType(Enum):
    """Type of content in the request."""
    TEXT = "text"
    VISION = "vision"      # Contains images
    AUDIO = "audio"        # Contains audio
    MULTIMODAL = "multimodal"  # Multiple content types


@dataclass
class ProviderMetrics:
    """Metrics for a single provider."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    last_request_time: Optional[str] = None
    last_error_time: Optional[str] = None
    consecutive_failures: int = 0
    
    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests
    
    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests


@dataclass
class ModelCapability:
    """Capabilities a model supports."""
    name: str
    supports_vision: bool = False
    supports_audio: bool = False
    supports_tools: bool = False
    supports_json: bool = False
    supports_streaming: bool = True
    context_window: int = 4096


@dataclass
class Provider:
    """LLM provider configuration and state."""
    name: str
    type: str  # ollama, openai, anthropic, airllm
    enabled: bool
    priority: int
    url: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: list[dict] = field(default_factory=list)
    
    # Runtime state
    status: ProviderStatus = ProviderStatus.HEALTHY
    metrics: ProviderMetrics = field(default_factory=ProviderMetrics)
    circuit_state: CircuitState = CircuitState.CLOSED
    circuit_opened_at: Optional[float] = None
    half_open_calls: int = 0
    
    def get_default_model(self) -> Optional[str]:
        """Get the default model for this provider."""
        for model in self.models:
            if model.get("default"):
                return model["name"]
        if self.models:
            return self.models[0]["name"]
        return None
    
    def get_model_with_capability(self, capability: str) -> Optional[str]:
        """Get a model that supports the given capability."""
        for model in self.models:
            capabilities = model.get("capabilities", [])
            if capability in capabilities:
                return model["name"]
        # Fall back to default
        return self.get_default_model()
    
    def model_has_capability(self, model_name: str, capability: str) -> bool:
        """Check if a specific model has a capability."""
        for model in self.models:
            if model["name"] == model_name:
                capabilities = model.get("capabilities", [])
                return capability in capabilities
        return False


@dataclass
class RouterConfig:
    """Cascade router configuration."""
    timeout_seconds: int = 30
    max_retries_per_provider: int = 2
    retry_delay_seconds: int = 1
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60
    circuit_breaker_half_open_max_calls: int = 2
    cost_tracking_enabled: bool = True
    budget_daily_usd: float = 10.0
    # Multi-modal settings
    auto_pull_models: bool = True
    fallback_chains: dict = field(default_factory=dict)


class CascadeRouter:
    """Routes LLM requests with automatic failover.
    
    Now with multi-modal support:
    - Automatically detects content type (text, vision, audio)
    - Selects appropriate models based on capabilities
    - Falls back through capability-specific model chains
    - Supports image URLs and base64 encoding
    
    Usage:
        router = CascadeRouter()
        
        # Text request
        response = await router.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="llama3.2"
        )
        
        # Vision request (automatically detects and selects vision model)
        response = await router.complete(
            messages=[{
                "role": "user",
                "content": "What's in this image?",
                "images": ["path/to/image.jpg"]
            }],
            model="llava:7b"
        )
        
        # Check metrics
        metrics = router.get_metrics()
    """
    
    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or Path("config/providers.yaml")
        self.providers: list[Provider] = []
        self.config: RouterConfig = RouterConfig()
        self._load_config()
        
        # Initialize multi-modal manager if available
        self._mm_manager: Optional[Any] = None
        try:
            from infrastructure.models.multimodal import get_multimodal_manager
            self._mm_manager = get_multimodal_manager()
        except Exception as exc:
            logger.debug("Multi-modal manager not available: %s", exc)
        
        logger.info("CascadeRouter initialized with %d providers", len(self.providers))
    
    def _load_config(self) -> None:
        """Load configuration from YAML."""
        if not self.config_path.exists():
            logger.warning("Config not found: %s, using defaults", self.config_path)
            return
        
        try:
            if yaml is None:
                raise RuntimeError("PyYAML not installed")
            
            content = self.config_path.read_text()
            # Expand environment variables
            content = self._expand_env_vars(content)
            data = yaml.safe_load(content)
            
            # Load cascade settings
            cascade = data.get("cascade", {})
            
            # Load fallback chains
            fallback_chains = data.get("fallback_chains", {})
            
            # Load multi-modal settings
            multimodal = data.get("multimodal", {})
            
            self.config = RouterConfig(
                timeout_seconds=cascade.get("timeout_seconds", 30),
                max_retries_per_provider=cascade.get("max_retries_per_provider", 2),
                retry_delay_seconds=cascade.get("retry_delay_seconds", 1),
                circuit_breaker_failure_threshold=cascade.get("circuit_breaker", {}).get("failure_threshold", 5),
                circuit_breaker_recovery_timeout=cascade.get("circuit_breaker", {}).get("recovery_timeout", 60),
                circuit_breaker_half_open_max_calls=cascade.get("circuit_breaker", {}).get("half_open_max_calls", 2),
                auto_pull_models=multimodal.get("auto_pull", True),
                fallback_chains=fallback_chains,
            )
            
            # Load providers
            for p_data in data.get("providers", []):
                # Skip disabled providers
                if not p_data.get("enabled", False):
                    continue
                
                provider = Provider(
                    name=p_data["name"],
                    type=p_data["type"],
                    enabled=p_data.get("enabled", True),
                    priority=p_data.get("priority", 99),
                    url=p_data.get("url"),
                    api_key=p_data.get("api_key"),
                    base_url=p_data.get("base_url"),
                    models=p_data.get("models", []),
                )
                
                # Check if provider is actually available
                if self._check_provider_available(provider):
                    self.providers.append(provider)
                else:
                    logger.warning("Provider %s not available, skipping", provider.name)
            
            # Sort by priority
            self.providers.sort(key=lambda p: p.priority)
            
        except Exception as exc:
            logger.error("Failed to load config: %s", exc)
    
    def _expand_env_vars(self, content: str) -> str:
        """Expand ${VAR} syntax in YAML content."""
        import os
        import re
        
        def replace_var(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        
        return re.sub(r"\$\{(\w+)\}", replace_var, content)
    
    def _check_provider_available(self, provider: Provider) -> bool:
        """Check if a provider is actually available."""
        if provider.type == "ollama":
            # Check if Ollama is running
            if requests is None:
                # Can't check without requests, assume available
                return True
            try:
                url = provider.url or "http://localhost:11434"
                response = requests.get(f"{url}/api/tags", timeout=5)
                return response.status_code == 200
            except Exception:
                return False
        
        elif provider.type == "airllm":
            # Check if airllm is installed
            try:
                import airllm
                return True
            except ImportError:
                return False
        
        elif provider.type in ("openai", "anthropic", "grok"):
            # Check if API key is set
            return provider.api_key is not None and provider.api_key != ""

        return True
    
    def _detect_content_type(self, messages: list[dict]) -> ContentType:
        """Detect the type of content in the messages.
        
        Checks for images, audio, etc. in the message content.
        """
        has_image = False
        has_audio = False
        
        for msg in messages:
            content = msg.get("content", "")
            
            # Check for image URLs/paths
            if msg.get("images"):
                has_image = True
            
            # Check for image URLs in content
            if isinstance(content, str):
                image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
                if any(ext in content.lower() for ext in image_extensions):
                    has_image = True
                if content.startswith("data:image/"):
                    has_image = True
            
            # Check for audio
            if msg.get("audio"):
                has_audio = True
            
            # Check for multimodal content structure
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "image_url":
                            has_image = True
                        elif item.get("type") == "audio":
                            has_audio = True
        
        if has_image and has_audio:
            return ContentType.MULTIMODAL
        elif has_image:
            return ContentType.VISION
        elif has_audio:
            return ContentType.AUDIO
        return ContentType.TEXT
    
    def _get_fallback_model(
        self, 
        provider: Provider, 
        original_model: str,
        content_type: ContentType
    ) -> Optional[str]:
        """Get a fallback model for the given content type."""
        # Map content type to capability
        capability_map = {
            ContentType.VISION: "vision",
            ContentType.AUDIO: "audio",
            ContentType.MULTIMODAL: "vision",  # Vision models often do both
        }
        
        capability = capability_map.get(content_type)
        if not capability:
            return None
        
        # Check provider's models for capability
        fallback_model = provider.get_model_with_capability(capability)
        if fallback_model and fallback_model != original_model:
            return fallback_model
        
        # Use fallback chains from config
        fallback_chain = self.config.fallback_chains.get(capability, [])
        for model_name in fallback_chain:
            if provider.model_has_capability(model_name, capability):
                return model_name
        
        return None
    
    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """Complete a chat conversation with automatic failover.
        
        Multi-modal support:
        - Automatically detects if messages contain images
        - Falls back to vision-capable models when needed
        - Supports image URLs, paths, and base64 encoding
        
        Args:
            messages: List of message dicts with role and content
            model: Preferred model (tries this first, then provider defaults)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        
        Returns:
            Dict with content, provider_used, and metrics
        
        Raises:
            RuntimeError: If all providers fail
        """
        # Detect content type for multi-modal routing
        content_type = self._detect_content_type(messages)
        if content_type != ContentType.TEXT:
            logger.debug("Detected %s content, selecting appropriate model", content_type.value)
        
        errors = []
        
        for provider in self.providers:
            # Skip disabled providers
            if not provider.enabled:
                logger.debug("Skipping %s (disabled)", provider.name)
                continue
            
            # Skip unhealthy providers (circuit breaker)
            if provider.status == ProviderStatus.UNHEALTHY:
                # Check if circuit breaker can close
                if self._can_close_circuit(provider):
                    provider.circuit_state = CircuitState.HALF_OPEN
                    provider.half_open_calls = 0
                    logger.info("Circuit breaker half-open for %s", provider.name)
                else:
                    logger.debug("Skipping %s (circuit open)", provider.name)
                    continue
            
            # Determine which model to use
            selected_model = model or provider.get_default_model()
            is_fallback_model = False
            
            # For non-text content, check if model supports it
            if content_type != ContentType.TEXT and selected_model:
                if provider.type == "ollama" and self._mm_manager:
                    from infrastructure.models.multimodal import ModelCapability
                    
                    # Check if selected model supports the required capability
                    if content_type == ContentType.VISION:
                        supports = self._mm_manager.model_supports(
                            selected_model, ModelCapability.VISION
                        )
                        if not supports:
                            # Find fallback model
                            fallback = self._get_fallback_model(
                                provider, selected_model, content_type
                            )
                            if fallback:
                                logger.info(
                                    "Model %s doesn't support vision, falling back to %s",
                                    selected_model, fallback
                                )
                                selected_model = fallback
                                is_fallback_model = True
                            else:
                                logger.warning(
                                    "No vision-capable model found on %s, trying anyway",
                                    provider.name
                                )
            
            # Try this provider
            for attempt in range(self.config.max_retries_per_provider):
                try:
                    result = await self._try_provider(
                        provider=provider,
                        messages=messages,
                        model=selected_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        content_type=content_type,
                    )
                    
                    # Success! Update metrics and return
                    self._record_success(provider, result.get("latency_ms", 0))
                    return {
                        "content": result["content"],
                        "provider": provider.name,
                        "model": result.get("model", selected_model or provider.get_default_model()),
                        "latency_ms": result.get("latency_ms", 0),
                        "is_fallback_model": is_fallback_model,
                    }
                    
                except Exception as exc:
                    error_msg = str(exc)
                    logger.warning(
                        "Provider %s attempt %d failed: %s",
                        provider.name, attempt + 1, error_msg
                    )
                    errors.append(f"{provider.name}: {error_msg}")
                    
                    if attempt < self.config.max_retries_per_provider - 1:
                        await asyncio.sleep(self.config.retry_delay_seconds)
            
            # All retries failed for this provider
            self._record_failure(provider)
        
        # All providers failed
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")
    
    async def _try_provider(
        self,
        provider: Provider,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        content_type: ContentType = ContentType.TEXT,
    ) -> dict:
        """Try a single provider request."""
        start_time = time.time()
        
        if provider.type == "ollama":
            result = await self._call_ollama(
                provider=provider,
                messages=messages,
                model=model or provider.get_default_model(),
                temperature=temperature,
                content_type=content_type,
            )
        elif provider.type == "openai":
            result = await self._call_openai(
                provider=provider,
                messages=messages,
                model=model or provider.get_default_model(),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider.type == "anthropic":
            result = await self._call_anthropic(
                provider=provider,
                messages=messages,
                model=model or provider.get_default_model(),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider.type == "grok":
            result = await self._call_grok(
                provider=provider,
                messages=messages,
                model=model or provider.get_default_model(),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            raise ValueError(f"Unknown provider type: {provider.type}")
        
        latency_ms = (time.time() - start_time) * 1000
        result["latency_ms"] = latency_ms
        
        return result
    
    async def _call_ollama(
        self,
        provider: Provider,
        messages: list[dict],
        model: str,
        temperature: float,
        content_type: ContentType = ContentType.TEXT,
    ) -> dict:
        """Call Ollama API with multi-modal support."""
        import aiohttp
        
        url = f"{provider.url}/api/chat"
        
        # Transform messages for Ollama format (including images)
        transformed_messages = self._transform_messages_for_ollama(messages)
        
        payload = {
            "model": model,
            "messages": transformed_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(f"Ollama error {response.status}: {text}")
                
                data = await response.json()
                return {
                    "content": data["message"]["content"],
                    "model": model,
                }
    
    def _transform_messages_for_ollama(self, messages: list[dict]) -> list[dict]:
        """Transform messages to Ollama format, handling images."""
        transformed = []
        
        for msg in messages:
            new_msg = {
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            }
            
            # Handle images
            images = msg.get("images", [])
            if images:
                new_msg["images"] = []
                for img in images:
                    if isinstance(img, str):
                        if img.startswith("data:image/"):
                            # Base64 encoded image
                            new_msg["images"].append(img.split(",")[1])
                        elif img.startswith("http://") or img.startswith("https://"):
                            # URL - would need to download, skip for now
                            logger.warning("Image URLs not yet supported, skipping: %s", img)
                        elif Path(img).exists():
                            # Local file path - read and encode
                            try:
                                with open(img, "rb") as f:
                                    img_data = base64.b64encode(f.read()).decode()
                                    new_msg["images"].append(img_data)
                            except Exception as exc:
                                logger.error("Failed to read image %s: %s", img, exc)
            
            transformed.append(new_msg)
        
        return transformed
    
    async def _call_openai(
        self,
        provider: Provider,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
    ) -> dict:
        """Call OpenAI API."""
        import openai
        
        client = openai.AsyncOpenAI(
            api_key=provider.api_key,
            base_url=provider.base_url,
            timeout=self.config.timeout_seconds,
        )
        
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        
        response = await client.chat.completions.create(**kwargs)
        
        return {
            "content": response.choices[0].message.content,
            "model": response.model,
        }
    
    async def _call_anthropic(
        self,
        provider: Provider,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
    ) -> dict:
        """Call Anthropic API."""
        import anthropic
        
        client = anthropic.AsyncAnthropic(
            api_key=provider.api_key,
            timeout=self.config.timeout_seconds,
        )
        
        # Convert messages to Anthropic format
        system_msg = None
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                conversation.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })
        
        kwargs = {
            "model": model,
            "messages": conversation,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
        }
        if system_msg:
            kwargs["system"] = system_msg
        
        response = await client.messages.create(**kwargs)
        
        return {
            "content": response.content[0].text,
            "model": response.model,
        }

    async def _call_grok(
        self,
        provider: Provider,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
    ) -> dict:
        """Call xAI Grok API via OpenAI-compatible SDK."""
        import httpx
        import openai

        client = openai.AsyncOpenAI(
            api_key=provider.api_key,
            base_url=provider.base_url or "https://api.x.ai/v1",
            timeout=httpx.Timeout(300.0),
        )

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = await client.chat.completions.create(**kwargs)

        return {
            "content": response.choices[0].message.content,
            "model": response.model,
        }
    
    def _record_success(self, provider: Provider, latency_ms: float) -> None:
        """Record a successful request."""
        provider.metrics.total_requests += 1
        provider.metrics.successful_requests += 1
        provider.metrics.total_latency_ms += latency_ms
        provider.metrics.last_request_time = datetime.now(timezone.utc).isoformat()
        provider.metrics.consecutive_failures = 0
        
        # Close circuit breaker if half-open
        if provider.circuit_state == CircuitState.HALF_OPEN:
            provider.half_open_calls += 1
            if provider.half_open_calls >= self.config.circuit_breaker_half_open_max_calls:
                self._close_circuit(provider)
        
        # Update status based on error rate
        if provider.metrics.error_rate < 0.1:
            provider.status = ProviderStatus.HEALTHY
        elif provider.metrics.error_rate < 0.3:
            provider.status = ProviderStatus.DEGRADED
    
    def _record_failure(self, provider: Provider) -> None:
        """Record a failed request."""
        provider.metrics.total_requests += 1
        provider.metrics.failed_requests += 1
        provider.metrics.last_error_time = datetime.now(timezone.utc).isoformat()
        provider.metrics.consecutive_failures += 1
        
        # Check if we should open circuit breaker
        if provider.metrics.consecutive_failures >= self.config.circuit_breaker_failure_threshold:
            self._open_circuit(provider)
        
        # Update status
        if provider.metrics.error_rate > 0.3:
            provider.status = ProviderStatus.DEGRADED
        if provider.metrics.error_rate > 0.5:
            provider.status = ProviderStatus.UNHEALTHY
    
    def _open_circuit(self, provider: Provider) -> None:
        """Open the circuit breaker for a provider."""
        provider.circuit_state = CircuitState.OPEN
        provider.circuit_opened_at = time.time()
        provider.status = ProviderStatus.UNHEALTHY
        logger.warning("Circuit breaker OPEN for %s", provider.name)
    
    def _can_close_circuit(self, provider: Provider) -> bool:
        """Check if circuit breaker can transition to half-open."""
        if provider.circuit_opened_at is None:
            return False
        elapsed = time.time() - provider.circuit_opened_at
        return elapsed >= self.config.circuit_breaker_recovery_timeout
    
    def _close_circuit(self, provider: Provider) -> None:
        """Close the circuit breaker (provider healthy again)."""
        provider.circuit_state = CircuitState.CLOSED
        provider.circuit_opened_at = None
        provider.half_open_calls = 0
        provider.metrics.consecutive_failures = 0
        provider.status = ProviderStatus.HEALTHY
        logger.info("Circuit breaker CLOSED for %s", provider.name)
    
    def get_metrics(self) -> dict:
        """Get metrics for all providers."""
        return {
            "providers": [
                {
                    "name": p.name,
                    "type": p.type,
                    "status": p.status.value,
                    "circuit_state": p.circuit_state.value,
                    "metrics": {
                        "total_requests": p.metrics.total_requests,
                        "successful": p.metrics.successful_requests,
                        "failed": p.metrics.failed_requests,
                        "error_rate": round(p.metrics.error_rate, 3),
                        "avg_latency_ms": round(p.metrics.avg_latency_ms, 2),
                    },
                }
                for p in self.providers
            ]
        }
    
    def get_status(self) -> dict:
        """Get current router status."""
        healthy = sum(1 for p in self.providers if p.status == ProviderStatus.HEALTHY)
        
        return {
            "total_providers": len(self.providers),
            "healthy_providers": healthy,
            "degraded_providers": sum(1 for p in self.providers if p.status == ProviderStatus.DEGRADED),
            "unhealthy_providers": sum(1 for p in self.providers if p.status == ProviderStatus.UNHEALTHY),
            "providers": [
                {
                    "name": p.name,
                    "type": p.type,
                    "status": p.status.value,
                    "priority": p.priority,
                    "default_model": p.get_default_model(),
                }
                for p in self.providers
            ],
        }
    
    async def generate_with_image(
        self,
        prompt: str,
        image_path: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> dict:
        """Convenience method for vision requests.
        
        Args:
            prompt: Text prompt about the image
            image_path: Path to image file
            model: Vision-capable model (auto-selected if not provided)
            temperature: Sampling temperature
            
        Returns:
            Response dict with content and metadata
        """
        messages = [{
            "role": "user",
            "content": prompt,
            "images": [image_path],
        }]
        return await self.complete(
            messages=messages,
            model=model,
            temperature=temperature,
        )


# Module-level singleton
cascade_router: Optional[CascadeRouter] = None


def get_router() -> CascadeRouter:
    """Get or create the cascade router singleton."""
    global cascade_router
    if cascade_router is None:
        cascade_router = CascadeRouter()
    return cascade_router
