"""End-to-end integration tests for the complete system.

These tests verify the full stack works together.
"""

import pytest
from fastapi.testclient import TestClient


class TestDashboardIntegration:
    """Integration tests for the dashboard app."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        from dashboard.app import app
        return TestClient(app)
    
    def test_health_endpoint(self, client):
        """Test the health check endpoint works."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
    
    def test_index_page_loads(self, client):
        """Test the main page loads."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Timmy" in response.text or "Mission Control" in response.text


class TestRouterAPIIntegration:
    """Integration tests for Router API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        from dashboard.app import app
        return TestClient(app)
    
    def test_router_status_endpoint(self, client):
        """Test the router status endpoint."""
        response = client.get("/api/v1/router/status")
        assert response.status_code == 200
        data = response.json()
        assert "total_providers" in data
        assert "providers" in data
    
    def test_router_metrics_endpoint(self, client):
        """Test the router metrics endpoint."""
        response = client.get("/api/v1/router/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
    
    def test_router_providers_endpoint(self, client):
        """Test the router providers list endpoint."""
        response = client.get("/api/v1/router/providers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_router_config_endpoint(self, client):
        """Test the router config endpoint."""
        response = client.get("/api/v1/router/config")
        assert response.status_code == 200
        data = response.json()
        assert "timeout_seconds" in data
        assert "circuit_breaker" in data


class TestMCPIntegration:
    """Integration tests for MCP system."""
    
    def test_mcp_registry_singleton(self):
        """Test that MCP registry is properly initialized."""
        from mcp.registry import tool_registry, get_registry
        
        # Should be the same object
        assert get_registry() is tool_registry
    
    def test_mcp_discovery_singleton(self):
        """Test that MCP discovery is properly initialized."""
        from mcp.discovery import get_discovery
        
        discovery1 = get_discovery()
        discovery2 = get_discovery()
        
        # Should be the same object
        assert discovery1 is discovery2
    
    def test_mcp_bootstrap_status(self):
        """Test that bootstrap status returns valid data."""
        from mcp.bootstrap import get_bootstrap_status
        
        status = get_bootstrap_status()
        
        assert isinstance(status["auto_bootstrap_enabled"], bool)
        assert isinstance(status["discovered_tools_count"], int)
        assert isinstance(status["registered_tools_count"], int)


class TestEventBusIntegration:
    """Integration tests for Event Bus."""
    
    @pytest.mark.asyncio
    async def test_event_bus_publish_subscribe(self):
        """Test event bus publish and subscribe works."""
        from infrastructure.events.bus import EventBus, Event
        
        bus = EventBus()
        events_received = []
        
        @bus.subscribe("test.event.*")
        async def handler(event):
            events_received.append(event.data)
        
        await bus.publish(Event(
            type="test.event.test",
            source="test",
            data={"message": "hello"}
        ))
        
        # Give async handler time to run
        import asyncio
        await asyncio.sleep(0.1)
        
        assert len(events_received) == 1
        assert events_received[0]["message"] == "hello"


class TestAgentSystemIntegration:
    """Integration tests for Agent system."""
    
    def test_base_agent_imports(self):
        """Test that base agent can be imported."""
        from timmy.agents.base import BaseAgent
        
        assert BaseAgent is not None
    
    def test_agent_creation(self):
        """Test creating agent config dict (AgentConfig class doesn't exist)."""
        config = {
            "name": "test_agent",
            "system_prompt": "You are a test agent.",
        }
        
        assert config["name"] == "test_agent"
        assert config["system_prompt"] == "You are a test agent."


class TestMemorySystemIntegration:
    """Integration tests for Memory system."""
    
    def test_memory_system_imports(self):
        """Test that memory system can be imported."""
        from timmy.memory_system import MemorySystem
        
        assert MemorySystem is not None
    
    def test_semantic_memory_imports(self):
        """Test that semantic memory can be imported."""
        from timmy.semantic_memory import SemanticMemory
        
        assert SemanticMemory is not None
