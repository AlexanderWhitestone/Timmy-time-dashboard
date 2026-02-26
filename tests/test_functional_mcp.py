"""Functional tests for MCP Discovery and Bootstrap - tests actual behavior.

These tests verify the MCP system works end-to-end.
"""

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp.discovery import ToolDiscovery, mcp_tool, DiscoveredTool
from mcp.bootstrap import auto_bootstrap, bootstrap_from_directory
from mcp.registry import ToolRegistry


class TestMCPToolDecoratorFunctional:
    """Functional tests for @mcp_tool decorator."""
    
    def test_decorator_marks_function(self):
        """Test that decorator properly marks function as tool."""
        @mcp_tool(name="my_tool", category="test", tags=["a", "b"])
        def my_function(x: str) -> str:
            """Do something."""
            return x
        
        assert hasattr(my_function, "_mcp_tool")
        assert my_function._mcp_tool is True
        assert my_function._mcp_name == "my_tool"
        assert my_function._mcp_category == "test"
        assert my_function._mcp_tags == ["a", "b"]
        assert "Do something" in my_function._mcp_description
    
    def test_decorator_uses_defaults(self):
        """Test decorator uses sensible defaults."""
        @mcp_tool()
        def another_function():
            pass
        
        assert another_function._mcp_name == "another_function"
        assert another_function._mcp_category == "general"
        assert another_function._mcp_tags == []


class TestToolDiscoveryFunctional:
    """Functional tests for tool discovery."""
    
    @pytest.fixture
    def mock_module(self):
        """Create a mock module with tools."""
        module = types.ModuleType("test_discovery_module")
        module.__file__ = "test_discovery_module.py"
        
        @mcp_tool(name="echo", category="test")
        def echo_func(message: str) -> str:
            """Echo a message."""
            return message
        
        @mcp_tool(name="add", category="math")
        def add_func(a: int, b: int) -> int:
            """Add numbers."""
            return a + b
        
        def not_a_tool():
            """Not decorated."""
            pass
        
        module.echo_func = echo_func
        module.add_func = add_func
        module.not_a_tool = not_a_tool
        
        sys.modules["test_discovery_module"] = module
        yield module
        del sys.modules["test_discovery_module"]
    
    def test_discover_module_finds_tools(self, mock_module):
        """Test discovering tools from a module."""
        registry = ToolRegistry()
        discovery = ToolDiscovery(registry=registry)
        
        tools = discovery.discover_module("test_discovery_module")
        
        names = [t.name for t in tools]
        assert "echo" in names
        assert "add" in names
        assert "not_a_tool" not in names
    
    def test_discovered_tool_has_correct_metadata(self, mock_module):
        """Test discovered tools have correct metadata."""
        registry = ToolRegistry()
        discovery = ToolDiscovery(registry=registry)
        
        tools = discovery.discover_module("test_discovery_module")
        
        echo = next(t for t in tools if t.name == "echo")
        assert echo.category == "test"
        assert "Echo a message" in echo.description
    
    def test_discovered_tool_has_schema(self, mock_module):
        """Test discovered tools have generated schemas."""
        registry = ToolRegistry()
        discovery = ToolDiscovery(registry=registry)
        
        tools = discovery.discover_module("test_discovery_module")
        
        add = next(t for t in tools if t.name == "add")
        assert "properties" in add.parameters_schema
        assert "a" in add.parameters_schema["properties"]
        assert "b" in add.parameters_schema["properties"]
    
    def test_discover_nonexistent_module(self):
        """Test discovering from non-existent module returns empty list."""
        registry = ToolRegistry()
        discovery = ToolDiscovery(registry=registry)
        
        tools = discovery.discover_module("nonexistent_xyz_module")
        
        assert tools == []


class TestToolRegistrationFunctional:
    """Functional tests for tool registration via discovery."""
    
    @pytest.fixture
    def mock_module(self):
        """Create a mock module with tools."""
        module = types.ModuleType("test_register_module")
        module.__file__ = "test_register_module.py"
        
        @mcp_tool(name="register_test", category="test")
        def test_func(value: str) -> str:
            """Test function."""
            return value.upper()
        
        module.test_func = test_func
        sys.modules["test_register_module"] = module
        yield module
        del sys.modules["test_register_module"]
    
    def test_auto_register_adds_to_registry(self, mock_module):
        """Test auto_register adds tools to registry."""
        registry = ToolRegistry()
        discovery = ToolDiscovery(registry=registry)
        
        registered = discovery.auto_register("test_register_module")
        
        assert "register_test" in registered
        assert registry.get("register_test") is not None
    
    def test_registered_tool_can_execute(self, mock_module):
        """Test that registered tools can be executed."""
        registry = ToolRegistry()
        discovery = ToolDiscovery(registry=registry)
        
        discovery.auto_register("test_register_module")
        
        result = asyncio.run(
            registry.execute("register_test", {"value": "hello"})
        )
        
        assert result == "HELLO"
    
    def test_registered_tool_tracks_metrics(self, mock_module):
        """Test that tool execution tracks metrics."""
        registry = ToolRegistry()
        discovery = ToolDiscovery(registry=registry)
        
        discovery.auto_register("test_register_module")
        
        # Execute multiple times
        for _ in range(3):
            asyncio.run(registry.execute("register_test", {"value": "test"}))
        
        metrics = registry.get_metrics("register_test")
        assert metrics["executions"] == 3
        assert metrics["health"] == "healthy"


class TestMCBootstrapFunctional:
    """Functional tests for MCP bootstrap."""
    
    def test_auto_bootstrap_empty_list(self):
        """Test auto_bootstrap with empty packages list."""
        registry = ToolRegistry()
        
        registered = auto_bootstrap(
            packages=[],
            registry=registry,
            force=True,
        )
        
        assert registered == []
    
    def test_auto_bootstrap_nonexistent_package(self):
        """Test auto_bootstrap with non-existent package."""
        registry = ToolRegistry()
        
        registered = auto_bootstrap(
            packages=["nonexistent_package_12345"],
            registry=registry,
            force=True,
        )
        
        assert registered == []
    
    def test_bootstrap_status(self):
        """Test get_bootstrap_status returns expected structure."""
        from mcp.bootstrap import get_bootstrap_status
        
        status = get_bootstrap_status()
        
        assert "auto_bootstrap_enabled" in status
        assert "discovered_tools_count" in status
        assert "registered_tools_count" in status
        assert "default_packages" in status


class TestRegistryIntegration:
    """Integration tests for registry with discovery."""
    
    def test_registry_discover_filtering(self):
        """Test registry discover method filters correctly."""
        registry = ToolRegistry()
        
        @mcp_tool(name="cat1", category="category1", tags=["tag1"])
        def func1():
            pass
        
        @mcp_tool(name="cat2", category="category2", tags=["tag2"])
        def func2():
            pass
        
        registry.register_tool(name="cat1", function=func1, category="category1", tags=["tag1"])
        registry.register_tool(name="cat2", function=func2, category="category2", tags=["tag2"])
        
        # Filter by category
        cat1_tools = registry.discover(category="category1")
        assert len(cat1_tools) == 1
        assert cat1_tools[0].name == "cat1"
        
        # Filter by tags
        tag1_tools = registry.discover(tags=["tag1"])
        assert len(tag1_tools) == 1
        assert tag1_tools[0].name == "cat1"
    
    def test_registry_to_dict(self):
        """Test registry export includes all fields."""
        registry = ToolRegistry()
        
        @mcp_tool(name="export_test", category="test", tags=["a"])
        def export_func():
            """Test export."""
            pass
        
        registry.register_tool(
            name="export_test",
            function=export_func,
            category="test",
            tags=["a"],
            source_module="test_module",
        )
        
        export = registry.to_dict()
        
        assert export["total_tools"] == 1
        assert export["auto_discovered_count"] == 1
        
        tool = export["tools"][0]
        assert tool["name"] == "export_test"
        assert tool["category"] == "test"
        assert tool["tags"] == ["a"]
        assert tool["source_module"] == "test_module"
        assert tool["auto_discovered"] is True
