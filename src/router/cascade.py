"""Cascade LLM Router — Automatic failover between providers.

Routes requests through an ordered list of LLM providers,
automatically failing over on rate limits or errors.
Tracks metrics for latency, errors, and cost.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
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


class CascadeRouter:
    """Routes LLM requests with automatic failover.
    
    Usage:
        router = CascadeRouter()
        
        response = await router.complete(
            messages=[{"role": "user", "content": "Hello"}],
            model="llama3.2"
        )
        
        # Check metrics
        metrics = router.get_metrics()
    """
    
    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or Path("config/providers.yaml")
        self.providers: list[Provider] = []
        self.config: RouterConfig = RouterConfig()
        self._load_config()
        
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
            self.config = RouterConfig(
                timeout_seconds=cascade.get("timeout_seconds", 30),
                max_retries_per_provider=cascade.get("max_retries_per_provider", 2),
                retry_delay_seconds=cascade.get("retry_delay_seconds", 1),
                circuit_breaker_failure_threshold=cascade.get("circuit_breaker", {}).get("failure_threshold", 5),
                circuit_breaker_recovery_timeout=cascade.get("circuit_breaker", {}).get("recovery_timeout", 60),
                circuit_breaker_half_open_max_calls=cascade.get("circuit_breaker", {}).get("half_open_max_calls", 2),
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
        
        elif provider.type in ("openai", "anthropic"):
            # Check if API key is set
            return provider.api_key is not None and provider.api_key != ""
        
        return True
    
    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """Complete a chat conversation with automatic failover.
        
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
        errors = []
        
        for provider in self.providers:
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
            
            # Try this provider
            for attempt in range(self.config.max_retries_per_provider):
                try:
                    result = await self._try_provider(
                        provider=provider,
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    
                    # Success! Update metrics and return
                    self._record_success(provider, result.get("latency_ms", 0))
                    return {
                        "content": result["content"],
                        "provider": provider.name,
                        "model": result.get("model", model or provider.get_default_model()),
                        "latency_ms": result.get("latency_ms", 0),
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
        model: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
    ) -> dict:
        """Try a single provider request."""
        start_time = time.time()
        
        if provider.type == "ollama":
            result = await self._call_ollama(
                provider=provider,
                messages=messages,
                model=model or provider.get_default_model(),
                temperature=temperature,
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
    ) -> dict:
        """Call Ollama API."""
        import aiohttp
        
        url = f"{provider.url}/api/chat"
        
        payload = {
            "model": model,
            "messages": messages,
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


# Module-level singleton
cascade_router: Optional[CascadeRouter] = None


def get_router() -> CascadeRouter:
    """Get or create the cascade router singleton."""
    global cascade_router
    if cascade_router is None:
        cascade_router = CascadeRouter()
    return cascade_router
