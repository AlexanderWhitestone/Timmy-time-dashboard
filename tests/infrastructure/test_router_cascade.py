"""Tests for Cascade LLM Router."""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from infrastructure.router.cascade import (
    CascadeRouter,
    CircuitState,
    Provider,
    ProviderMetrics,
    ProviderStatus,
    RouterConfig,
)


class TestProviderMetrics:
    """Test provider metrics tracking."""

    def test_empty_metrics(self):
        """Test metrics with no requests."""
        metrics = ProviderMetrics()
        assert metrics.total_requests == 0
        assert metrics.avg_latency_ms == 0.0
        assert metrics.error_rate == 0.0

    def test_avg_latency_calculation(self):
        """Test average latency calculation."""
        metrics = ProviderMetrics(
            total_requests=4,
            total_latency_ms=1000.0,  # 4 requests, 1000ms total
        )
        assert metrics.avg_latency_ms == 250.0

    def test_error_rate_calculation(self):
        """Test error rate calculation."""
        metrics = ProviderMetrics(
            total_requests=10,
            successful_requests=7,
            failed_requests=3,
        )
        assert metrics.error_rate == 0.3


class TestProvider:
    """Test Provider dataclass."""

    def test_get_default_model(self):
        """Test getting default model."""
        provider = Provider(
            name="test",
            type="ollama",
            enabled=True,
            priority=1,
            models=[
                {"name": "llama3", "default": True},
                {"name": "mistral"},
            ],
        )
        assert provider.get_default_model() == "llama3"

    def test_get_default_model_no_default(self):
        """Test getting first model when no default set."""
        provider = Provider(
            name="test",
            type="ollama",
            enabled=True,
            priority=1,
            models=[
                {"name": "llama3"},
                {"name": "mistral"},
            ],
        )
        assert provider.get_default_model() == "llama3"

    def test_get_default_model_empty(self):
        """Test with no models."""
        provider = Provider(
            name="test",
            type="ollama",
            enabled=True,
            priority=1,
            models=[],
        )
        assert provider.get_default_model() is None


class TestRouterConfig:
    """Test router configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RouterConfig()
        assert config.timeout_seconds == 30
        assert config.max_retries_per_provider == 2
        assert config.retry_delay_seconds == 1
        assert config.circuit_breaker_failure_threshold == 5


class TestCascadeRouterInit:
    """Test CascadeRouter initialization."""

    def test_init_without_config(self, tmp_path):
        """Test initialization without config file."""
        router = CascadeRouter(config_path=tmp_path / "nonexistent.yaml")
        assert len(router.providers) == 0
        assert router.config.timeout_seconds == 30

    def test_init_with_config(self, tmp_path):
        """Test initialization with config file."""
        config = {
            "cascade": {
                "timeout_seconds": 60,
                "max_retries_per_provider": 3,
            },
            "providers": [
                {
                    "name": "test-ollama",
                    "type": "ollama",
                    "enabled": False,  # Disabled to avoid availability check
                    "priority": 1,
                    "url": "http://localhost:11434",
                }
            ],
        }
        config_path = tmp_path / "providers.yaml"
        config_path.write_text(yaml.dump(config))

        router = CascadeRouter(config_path=config_path)
        assert router.config.timeout_seconds == 60
        assert router.config.max_retries_per_provider == 3
        assert len(router.providers) == 0  # Provider is disabled

    def test_env_var_expansion(self, tmp_path, monkeypatch):
        """Test environment variable expansion in config."""
        monkeypatch.setenv("TEST_API_KEY", "secret123")

        config = {
            "cascade": {},
            "providers": [
                {
                    "name": "test-openai",
                    "type": "openai",
                    "enabled": True,
                    "priority": 1,
                    "api_key": "${TEST_API_KEY}",
                }
            ],
        }
        config_path = tmp_path / "providers.yaml"
        config_path.write_text(yaml.dump(config))

        router = CascadeRouter(config_path=config_path)
        assert len(router.providers) == 1
        assert router.providers[0].api_key == "secret123"


class TestCascadeRouterMetrics:
    """Test metrics tracking."""

    def test_record_success(self):
        """Test recording successful request."""
        provider = Provider(name="test", type="ollama", enabled=True, priority=1)

        router = CascadeRouter(config_path=Path("/nonexistent"))
        router._record_success(provider, 150.0)

        assert provider.metrics.total_requests == 1
        assert provider.metrics.successful_requests == 1
        assert provider.metrics.total_latency_ms == 150.0
        assert provider.metrics.consecutive_failures == 0

    def test_record_failure(self):
        """Test recording failed request."""
        provider = Provider(name="test", type="ollama", enabled=True, priority=1)

        router = CascadeRouter(config_path=Path("/nonexistent"))
        router._record_failure(provider)

        assert provider.metrics.total_requests == 1
        assert provider.metrics.failed_requests == 1
        assert provider.metrics.consecutive_failures == 1

    def test_circuit_breaker_opens(self):
        """Test circuit breaker opens after failures."""
        provider = Provider(name="test", type="ollama", enabled=True, priority=1)

        router = CascadeRouter(config_path=Path("/nonexistent"))
        router.config.circuit_breaker_failure_threshold = 3

        # Record 3 failures
        for _ in range(3):
            router._record_failure(provider)

        assert provider.circuit_state == CircuitState.OPEN
        assert provider.status == ProviderStatus.UNHEALTHY
        assert provider.circuit_opened_at is not None

    def test_circuit_breaker_can_close(self):
        """Test circuit breaker can transition to closed."""
        provider = Provider(name="test", type="ollama", enabled=True, priority=1)

        router = CascadeRouter(config_path=Path("/nonexistent"))
        router.config.circuit_breaker_failure_threshold = 3
        router.config.circuit_breaker_recovery_timeout = 0.1

        # Open the circuit
        for _ in range(3):
            router._record_failure(provider)

        assert provider.circuit_state == CircuitState.OPEN

        # Wait for recovery timeout (reduced for faster tests)
        import time

        time.sleep(0.2)

        # Check if can close
        assert router._can_close_circuit(provider) is True

    def test_half_open_to_closed(self):
        """Test circuit breaker closes after successful test calls."""
        provider = Provider(name="test", type="ollama", enabled=True, priority=1)

        router = CascadeRouter(config_path=Path("/nonexistent"))
        router.config.circuit_breaker_half_open_max_calls = 2

        # Manually set to half-open
        provider.circuit_state = CircuitState.HALF_OPEN
        provider.half_open_calls = 0

        # Record successful calls
        router._record_success(provider, 100.0)
        assert provider.circuit_state == CircuitState.HALF_OPEN  # Still half-open

        router._record_success(provider, 100.0)
        assert provider.circuit_state == CircuitState.CLOSED  # Now closed
        assert provider.status == ProviderStatus.HEALTHY


class TestCascadeRouterGetMetrics:
    """Test get_metrics method."""

    def test_get_metrics_empty(self):
        """Test getting metrics with no providers."""
        router = CascadeRouter(config_path=Path("/nonexistent"))
        metrics = router.get_metrics()

        assert "providers" in metrics
        assert len(metrics["providers"]) == 0

    def test_get_metrics_with_providers(self):
        """Test getting metrics with providers."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        # Add a test provider
        provider = Provider(
            name="test",
            type="ollama",
            enabled=True,
            priority=1,
        )
        provider.metrics.total_requests = 10
        provider.metrics.successful_requests = 8
        provider.metrics.failed_requests = 2
        provider.metrics.total_latency_ms = 2000.0

        router.providers = [provider]

        metrics = router.get_metrics()

        assert len(metrics["providers"]) == 1
        p_metrics = metrics["providers"][0]
        assert p_metrics["name"] == "test"
        assert p_metrics["metrics"]["total_requests"] == 10
        assert p_metrics["metrics"]["error_rate"] == 0.2
        assert p_metrics["metrics"]["avg_latency_ms"] == 200.0


class TestCascadeRouterGetStatus:
    """Test get_status method."""

    def test_get_status(self):
        """Test getting router status."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider = Provider(
            name="test",
            type="ollama",
            enabled=True,
            priority=1,
            models=[{"name": "llama3", "default": True}],
        )
        router.providers = [provider]

        status = router.get_status()

        assert status["total_providers"] == 1
        assert status["healthy_providers"] == 1
        assert status["degraded_providers"] == 0
        assert status["unhealthy_providers"] == 0
        assert len(status["providers"]) == 1


@pytest.mark.asyncio
class TestCascadeRouterComplete:
    """Test complete method with failover."""

    async def test_complete_with_ollama(self):
        """Test successful completion with Ollama."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider = Provider(
            name="ollama-local",
            type="ollama",
            enabled=True,
            priority=1,
            url="http://localhost:11434",
            models=[{"name": "llama3.2", "default": True}],
        )
        router.providers = [provider]

        # Mock the Ollama call
        with patch.object(router, "_call_ollama") as mock_call:
            mock_call.return_value = AsyncMock()()
            mock_call.return_value = {
                "content": "Hello, world!",
                "model": "llama3.2",
            }

            result = await router.complete(
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert result["content"] == "Hello, world!"
        assert result["provider"] == "ollama-local"
        assert result["model"] == "llama3.2"

    async def test_failover_to_second_provider(self):
        """Test failover when first provider fails."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider1 = Provider(
            name="ollama-failing",
            type="ollama",
            enabled=True,
            priority=1,
            url="http://localhost:11434",
            models=[{"name": "llama3.2", "default": True}],
        )
        provider2 = Provider(
            name="ollama-backup",
            type="ollama",
            enabled=True,
            priority=2,
            url="http://backup:11434",
            models=[{"name": "llama3.2", "default": True}],
        )
        router.providers = [provider1, provider2]

        # First provider fails, second succeeds
        call_count = [0]

        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            # First 2 retries for provider1 fail, then provider2 succeeds
            if call_count[0] <= router.config.max_retries_per_provider:
                raise RuntimeError("Connection failed")
            return {"content": "Backup response", "model": "llama3.2"}

        with patch.object(router, "_call_ollama") as mock_call:
            mock_call.side_effect = side_effect

            result = await router.complete(
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert result["content"] == "Backup response"
        assert result["provider"] == "ollama-backup"

    async def test_all_providers_fail(self):
        """Test error when all providers fail."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider = Provider(
            name="failing",
            type="ollama",
            enabled=True,
            priority=1,
            models=[{"name": "llama3.2", "default": True}],
        )
        router.providers = [provider]

        with patch.object(router, "_call_ollama") as mock_call:
            mock_call.side_effect = RuntimeError("Always fails")

            with pytest.raises(RuntimeError) as exc_info:
                await router.complete(messages=[{"role": "user", "content": "Hi"}])

            assert "All providers failed" in str(exc_info.value)

    async def test_skips_unhealthy_provider(self):
        """Test that unhealthy providers are skipped."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider1 = Provider(
            name="unhealthy",
            type="ollama",
            enabled=True,
            priority=1,
            status=ProviderStatus.UNHEALTHY,
            circuit_state=CircuitState.OPEN,
            circuit_opened_at=time.time(),  # Just opened
            models=[{"name": "llama3.2", "default": True}],
        )
        provider2 = Provider(
            name="healthy",
            type="ollama",
            enabled=True,
            priority=2,
            models=[{"name": "llama3.2", "default": True}],
        )
        router.providers = [provider1, provider2]

        with patch.object(router, "_call_ollama") as mock_call:
            mock_call.return_value = {"content": "Success", "model": "llama3.2"}

            result = await router.complete(
                messages=[{"role": "user", "content": "Hi"}],
            )

        # Should use the healthy provider
        assert result["provider"] == "healthy"


class TestProviderAvailabilityCheck:
    """Test provider availability checking."""

    def test_check_ollama_without_requests(self):
        """Test Ollama returns True when requests not available (fallback)."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider = Provider(
            name="ollama",
            type="ollama",
            enabled=True,
            priority=1,
            url="http://localhost:11434",
        )

        # When requests is None, assume available
        import infrastructure.router.cascade as cascade_module

        old_requests = cascade_module.requests
        cascade_module.requests = None
        try:
            assert router._check_provider_available(provider) is True
        finally:
            cascade_module.requests = old_requests

    def test_check_openai_with_key(self):
        """Test OpenAI with API key."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider = Provider(
            name="openai",
            type="openai",
            enabled=True,
            priority=1,
            api_key="sk-test123",
        )

        assert router._check_provider_available(provider) is True

    def test_check_openai_without_key(self):
        """Test OpenAI without API key."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider = Provider(
            name="openai",
            type="openai",
            enabled=True,
            priority=1,
            api_key=None,
        )

        assert router._check_provider_available(provider) is False

    def test_check_airllm_installed(self):
        """Test AirLLM when installed."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider = Provider(
            name="airllm",
            type="airllm",
            enabled=True,
            priority=1,
        )

        with patch("builtins.__import__") as mock_import:
            mock_import.return_value = MagicMock()
            assert router._check_provider_available(provider) is True

    def test_check_airllm_not_installed(self):
        """Test AirLLM when not installed."""
        router = CascadeRouter(config_path=Path("/nonexistent"))

        provider = Provider(
            name="airllm",
            type="airllm",
            enabled=True,
            priority=1,
        )

        # Patch __import__ to simulate airllm not being available
        def raise_import_error(name, *args, **kwargs):
            if name == "airllm":
                raise ImportError("No module named 'airllm'")
            return __builtins__.__import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=raise_import_error):
            assert router._check_provider_available(provider) is False
