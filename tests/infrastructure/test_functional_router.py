"""Functional tests for Cascade Router - tests actual behavior.

These tests verify the router works end-to-end with mocked external services.
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrastructure.router.cascade import CascadeRouter, Provider, ProviderStatus, CircuitState


class TestCascadeRouterFunctional:
    """Functional tests for Cascade Router with mocked providers."""
    
    @pytest.fixture
    def router(self):
        """Create a router with no config file."""
        return CascadeRouter(config_path=Path("/nonexistent"))
    
    @pytest.fixture
    def mock_healthy_provider(self):
        """Create a mock healthy provider."""
        provider = Provider(
            name="test-healthy",
            type="test",
            enabled=True,
            priority=1,
            models=[{"name": "test-model", "default": True}],
        )
        return provider
    
    @pytest.fixture
    def mock_failing_provider(self):
        """Create a mock failing provider."""
        provider = Provider(
            name="test-failing",
            type="test",
            enabled=True,
            priority=1,
            models=[{"name": "test-model", "default": True}],
        )
        return provider
    
    @pytest.mark.asyncio
    async def test_successful_completion_single_provider(self, router, mock_healthy_provider):
        """Test successful completion with a single working provider."""
        router.providers = [mock_healthy_provider]
        
        # Mock the provider's call method
        with patch.object(router, "_try_provider") as mock_try:
            mock_try.return_value = {
                "content": "Hello, world!",
                "model": "test-model",
                "latency_ms": 100.0,
            }
            
            result = await router.complete(
                messages=[{"role": "user", "content": "Hi"}],
            )
        
        assert result["content"] == "Hello, world!"
        assert result["provider"] == "test-healthy"
        assert result["model"] == "test-model"
        assert result["latency_ms"] == 100.0
    
    @pytest.mark.asyncio
    async def test_failover_to_second_provider(self, router):
        """Test failover when first provider fails."""
        provider1 = Provider(
            name="failing",
            type="test",
            enabled=True,
            priority=1,
            models=[{"name": "model", "default": True}],
        )
        provider2 = Provider(
            name="backup",
            type="test",
            enabled=True,
            priority=2,
            models=[{"name": "model", "default": True}],
        )
        router.providers = [provider1, provider2]
        
        call_count = [0]
        
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= router.config.max_retries_per_provider:
                raise RuntimeError("Connection failed")
            return {"content": "Backup works!", "model": "model"}
        
        with patch.object(router, "_try_provider", side_effect=side_effect):
            result = await router.complete(
                messages=[{"role": "user", "content": "Hi"}],
            )
        
        assert result["content"] == "Backup works!"
        assert result["provider"] == "backup"
    
    @pytest.mark.asyncio
    async def test_all_providers_fail_raises_error(self, router):
        """Test that RuntimeError is raised when all providers fail."""
        provider = Provider(
            name="always-fails",
            type="test",
            enabled=True,
            priority=1,
            models=[{"name": "model", "default": True}],
        )
        router.providers = [provider]
        
        with patch.object(router, "_try_provider") as mock_try:
            mock_try.side_effect = RuntimeError("Always fails")
            
            with pytest.raises(RuntimeError) as exc_info:
                await router.complete(messages=[{"role": "user", "content": "Hi"}])
            
            assert "All providers failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self, router):
        """Test circuit breaker opens after threshold failures."""
        provider = Provider(
            name="test",
            type="test",
            enabled=True,
            priority=1,
            models=[{"name": "model", "default": True}],
        )
        router.providers = [provider]
        router.config.circuit_breaker_failure_threshold = 3
        
        # Record 3 failures
        for _ in range(3):
            router._record_failure(provider)
        
        assert provider.circuit_state == CircuitState.OPEN
        assert provider.status == ProviderStatus.UNHEALTHY
    
    def test_metrics_tracking(self, router):
        """Test that metrics are tracked correctly."""
        provider = Provider(
            name="test",
            type="test",
            enabled=True,
            priority=1,
        )
        router.providers = [provider]
        
        # Record some successes and failures
        router._record_success(provider, 100.0)
        router._record_success(provider, 200.0)
        router._record_failure(provider)
        
        metrics = router.get_metrics()
        
        assert len(metrics["providers"]) == 1
        p_metrics = metrics["providers"][0]
        assert p_metrics["metrics"]["total_requests"] == 3
        assert p_metrics["metrics"]["successful"] == 2
        assert p_metrics["metrics"]["failed"] == 1
        # Average latency is over ALL requests (including failures with 0 latency)
        assert p_metrics["metrics"]["avg_latency_ms"] == 100.0  # (100+200+0)/3
    
    @pytest.mark.asyncio
    async def test_skips_disabled_providers(self, router):
        """Test that disabled providers are skipped."""
        disabled = Provider(
            name="disabled",
            type="test",
            enabled=False,
            priority=1,
            models=[{"name": "model", "default": True}],
        )
        enabled = Provider(
            name="enabled",
            type="test",
            enabled=True,
            priority=2,
            models=[{"name": "model", "default": True}],
        )
        router.providers = [disabled, enabled]
        
        # The router should try enabled provider
        with patch.object(router, "_try_provider") as mock_try:
            mock_try.return_value = {"content": "Success", "model": "model"}
            
            result = await router.complete(messages=[{"role": "user", "content": "Hi"}])
        
        assert result["provider"] == "enabled"


class TestProviderAvailability:
    """Test provider availability checking."""
    
    @pytest.fixture
    def router(self):
        return CascadeRouter(config_path=Path("/nonexistent"))
    
    def test_openai_available_with_key(self, router):
        """Test OpenAI provider is available when API key is set."""
        provider = Provider(
            name="openai",
            type="openai",
            enabled=True,
            priority=1,
            api_key="sk-test123",
        )
        
        assert router._check_provider_available(provider) is True
    
    def test_openai_unavailable_without_key(self, router):
        """Test OpenAI provider is unavailable without API key."""
        provider = Provider(
            name="openai",
            type="openai",
            enabled=True,
            priority=1,
            api_key=None,
        )
        
        assert router._check_provider_available(provider) is False
    
    def test_anthropic_available_with_key(self, router):
        """Test Anthropic provider is available when API key is set."""
        provider = Provider(
            name="anthropic",
            type="anthropic",
            enabled=True,
            priority=1,
            api_key="sk-test123",
        )
        
        assert router._check_provider_available(provider) is True


class TestRouterConfigLoading:
    """Test router configuration loading."""
    
    def test_loads_timeout_from_config(self, tmp_path):
        """Test that timeout is loaded from config."""
        import yaml
        
        config = {
            "cascade": {
                "timeout_seconds": 60,
                "max_retries_per_provider": 3,
            },
            "providers": [],
        }
        
        config_path = tmp_path / "providers.yaml"
        config_path.write_text(yaml.dump(config))
        
        router = CascadeRouter(config_path=config_path)
        
        assert router.config.timeout_seconds == 60
        assert router.config.max_retries_per_provider == 3
    
    def test_uses_defaults_without_config(self):
        """Test that defaults are used when config file doesn't exist."""
        router = CascadeRouter(config_path=Path("/nonexistent"))
        
        assert router.config.timeout_seconds == 30
        assert router.config.max_retries_per_provider == 2
