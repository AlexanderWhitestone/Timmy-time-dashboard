"""Tests for Cascade Router API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from router.cascade import CircuitState, Provider, ProviderStatus
from router.api import router, get_cascade_router


def make_mock_router():
    """Create a mock CascadeRouter."""
    router = MagicMock()
    
    # Create test providers
    provider1 = Provider(
        name="ollama-local",
        type="ollama",
        enabled=True,
        priority=1,
        url="http://localhost:11434",
        models=[{"name": "llama3.2", "default": True, "context_window": 128000}],
    )
    provider1.status = ProviderStatus.HEALTHY
    provider1.circuit_state = CircuitState.CLOSED
    
    provider2 = Provider(
        name="openai-backup",
        type="openai",
        enabled=True,
        priority=2,
        api_key="sk-test",
        models=[{"name": "gpt-4o-mini", "default": True, "context_window": 128000}],
    )
    provider2.status = ProviderStatus.DEGRADED
    provider2.circuit_state = CircuitState.CLOSED
    
    router.providers = [provider1, provider2]
    router.config.timeout_seconds = 30
    router.config.max_retries_per_provider = 2
    router.config.circuit_breaker_failure_threshold = 5
    
    return router


@pytest.fixture
def mock_router():
    """Create test client with mocked router."""
    from fastapi import FastAPI
    
    app = FastAPI()
    app.include_router(router)
    
    # Create mock router
    mock = make_mock_router()
    
    # Override dependency
    async def mock_get_router():
        return mock
    
    app.dependency_overrides[get_cascade_router] = mock_get_router
    
    client = TestClient(app)
    return client, mock


class TestCompleteEndpoint:
    """Test /complete endpoint."""
    
    def test_complete_success(self, mock_router):
        """Test successful completion."""
        client, mock = mock_router
        mock.complete = AsyncMock(return_value={
            "content": "Hello! How can I help?",
            "provider": "ollama-local",
            "model": "llama3.2",
            "latency_ms": 250.5,
        })
        
        response = client.post("/api/v1/router/complete", json={
            "messages": [{"role": "user", "content": "Hi"}],
            "model": "llama3.2",
            "temperature": 0.7,
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Hello! How can I help?"
        assert data["provider"] == "ollama-local"
        assert data["latency_ms"] == 250.5
    
    def test_complete_all_providers_fail(self, mock_router):
        """Test 503 when all providers fail."""
        client, mock = mock_router
        mock.complete = AsyncMock(side_effect=RuntimeError("All providers failed"))
        
        response = client.post("/api/v1/router/complete", json={
            "messages": [{"role": "user", "content": "Hi"}],
        })
        
        assert response.status_code == 503
        assert "All providers failed" in response.json()["detail"]
    
    def test_complete_default_temperature(self, mock_router):
        """Test completion with default temperature."""
        client, mock = mock_router
        mock.complete = AsyncMock(return_value={
            "content": "Response",
            "provider": "ollama-local",
            "model": "llama3.2",
            "latency_ms": 100.0,
        })
        
        response = client.post("/api/v1/router/complete", json={
            "messages": [{"role": "user", "content": "Hi"}],
        })
        
        assert response.status_code == 200
        # Check that complete was called with correct temperature
        call_args = mock.complete.call_args
        assert call_args.kwargs["temperature"] == 0.7


class TestStatusEndpoint:
    """Test /status endpoint."""
    
    def test_get_status(self, mock_router):
        """Test getting router status."""
        client, mock = mock_router
        mock.get_status = MagicMock(return_value={
            "total_providers": 2,
            "healthy_providers": 1,
            "degraded_providers": 1,
            "unhealthy_providers": 0,
            "providers": [
                {
                    "name": "ollama-local",
                    "type": "ollama",
                    "status": "healthy",
                    "priority": 1,
                    "default_model": "llama3.2",
                },
                {
                    "name": "openai-backup",
                    "type": "openai",
                    "status": "degraded",
                    "priority": 2,
                    "default_model": "gpt-4o-mini",
                },
            ],
        })
        
        response = client.get("/api/v1/router/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_providers"] == 2
        assert data["healthy_providers"] == 1
        assert data["degraded_providers"] == 1
        assert len(data["providers"]) == 2


class TestMetricsEndpoint:
    """Test /metrics endpoint."""
    
    def test_get_metrics(self, mock_router):
        """Test getting detailed metrics."""
        client, mock = mock_router
        # Setup the mock return value on the mock_router object
        mock.get_metrics = MagicMock(return_value={
            "providers": [
                {
                    "name": "ollama-local",
                    "type": "ollama",
                    "status": "healthy",
                    "circuit_state": "closed",
                    "metrics": {
                        "total_requests": 100,
                        "successful": 98,
                        "failed": 2,
                        "error_rate": 0.02,
                        "avg_latency_ms": 150.5,
                    },
                },
            ],
        })
        
        response = client.get("/api/v1/router/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["providers"]) == 1
        metrics = data["providers"][0]["metrics"]
        assert metrics["total_requests"] == 100
        assert metrics["error_rate"] == 0.02
        assert metrics["avg_latency_ms"] == 150.5


class TestListProvidersEndpoint:
    """Test /providers endpoint."""
    
    def test_list_providers(self, mock_router):
        """Test listing all providers."""
        client, mock = mock_router
        
        response = client.get("/api/v1/router/providers")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        
        # Check first provider
        assert data[0]["name"] == "ollama-local"
        assert data[0]["type"] == "ollama"
        assert data[0]["enabled"] is True
        assert data[0]["priority"] == 1
        assert data[0]["default_model"] == "llama3.2"
        assert "llama3.2" in data[0]["models"]


class TestControlProviderEndpoint:
    """Test /providers/{name}/control endpoint."""
    
    def test_disable_provider(self, mock_router):
        """Test disabling a provider."""
        client, mock = mock_router
        
        response = client.post(
            "/api/v1/router/providers/ollama-local/control",
            json={"action": "disable"}
        )
        
        assert response.status_code == 200
        assert "disabled" in response.json()["message"]
        
        # Check that the provider was disabled
        provider = mock.providers[0]
        assert provider.enabled is False
        assert provider.status == ProviderStatus.DISABLED
    
    def test_enable_provider(self, mock_router):
        """Test enabling a provider."""
        client, mock = mock_router
        # First disable it
        mock.providers[0].enabled = False
        mock.providers[0].status = ProviderStatus.DISABLED
        
        response = client.post(
            "/api/v1/router/providers/ollama-local/control",
            json={"action": "enable"}
        )
        
        assert response.status_code == 200
        assert "enabled" in response.json()["message"]
        assert mock.providers[0].enabled is True
    
    def test_reset_circuit(self, mock_router):
        """Test resetting circuit breaker."""
        client, mock = mock_router
        # Set to open state
        mock.providers[0].circuit_state = CircuitState.OPEN
        mock.providers[0].status = ProviderStatus.UNHEALTHY
        mock.providers[0].metrics.consecutive_failures = 10
        
        response = client.post(
            "/api/v1/router/providers/ollama-local/control",
            json={"action": "reset_circuit"}
        )
        
        assert response.status_code == 200
        assert "reset" in response.json()["message"]
        
        provider = mock.providers[0]
        assert provider.circuit_state == CircuitState.CLOSED
        assert provider.status == ProviderStatus.HEALTHY
        assert provider.metrics.consecutive_failures == 0
    
    def test_control_unknown_provider(self, mock_router):
        """Test controlling unknown provider returns 404."""
        client, mock = mock_router
        response = client.post(
            "/api/v1/router/providers/unknown/control",
            json={"action": "disable"}
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_control_unknown_action(self, mock_router):
        """Test unknown action returns 400."""
        client, mock = mock_router
        response = client.post(
            "/api/v1/router/providers/ollama-local/control",
            json={"action": "invalid_action"}
        )
        
        assert response.status_code == 400
        assert "Unknown action" in response.json()["detail"]


class TestHealthCheckEndpoint:
    """Test /health-check endpoint."""
    
    def test_health_check_all_healthy(self, mock_router):
        """Test health check when all providers are healthy."""
        client, mock = mock_router
        
        with patch.object(mock, "_check_provider_available") as mock_check:
            mock_check.return_value = True
            
            response = client.post("/api/v1/router/health-check")
        
        assert response.status_code == 200
        data = response.json()
        assert data["healthy_count"] == 2
        assert len(data["providers"]) == 2
        
        for p in data["providers"]:
            assert p["healthy"] is True
    
    def test_health_check_with_failure(self, mock_router):
        """Test health check when some providers fail."""
        client, mock = mock_router
        
        with patch.object(mock, "_check_provider_available") as mock_check:
            # First provider fails, second succeeds
            mock_check.side_effect = [False, True]
            
            response = client.post("/api/v1/router/health-check")
        
        assert response.status_code == 200
        data = response.json()
        assert data["healthy_count"] == 1
        assert data["providers"][0]["healthy"] is False
        assert data["providers"][1]["healthy"] is True


class TestGetConfigEndpoint:
    """Test /config endpoint."""
    
    def test_get_config(self, mock_router):
        """Test getting router configuration."""
        client, mock = mock_router
        
        response = client.get("/api/v1/router/config")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["timeout_seconds"] == 30
        assert data["max_retries_per_provider"] == 2
        assert "circuit_breaker" in data
        assert data["circuit_breaker"]["failure_threshold"] == 5
        
        # Check providers list (without secrets)
        assert len(data["providers"]) == 2
        assert "api_key" not in data["providers"][0]
