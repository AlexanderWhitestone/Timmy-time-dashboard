"""Tests for MCP Tool Auto-Discovery.

Tests follow pytest best practices:
- No module-level state
- Proper fixture cleanup
- Isolated tests
"""

import ast
import inspect
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp.discovery import DiscoveredTool, ToolDiscovery, mcp_tool
from mcp.registry import ToolRegistry


@pytest.fixture
def fresh_registry():
    """Create a fresh registry for each test."""
    return ToolRegistry()


@pytest.fixture
def discovery(fresh_registry):
    """Create a fresh discovery instance for each test."""
    return ToolDiscovery(registry=fresh_registry)


@pytest.fixture
def mock_module_with_tools():
    """Create a mock module with MCP tools for testing."""
    # Create a fresh module
    mock_module = types.ModuleType("mock_test_module")
    mock_module.__file__ = "mock_test_module.py"
    
    # Add decorated functions
    @mcp_tool(name="echo", category="test", tags=["utility"])
    def echo_func(message: str) -> str:
        """Echo a message back."""
        return message
    
    @mcp_tool(category="math")
    def add_func(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    
    def not_decorated():
        """Not a tool."""
        pass
    
    mock_module.echo_func = echo_func
    mock_module.add_func = add_func
    mock_module.not_decorated = not_decorated
    
    # Inject into sys.modules
    sys.modules["mock_test_module"] = mock_module
    
    yield mock_module
    
    # Cleanup
    del sys.modules["mock_test_module"]


class TestMCPToolDecorator:
    """Test the @mcp_tool decorator."""
    
    def test_decorator_sets_explicit_name(self):
        """Test that decorator uses explicit name."""
        @mcp_tool(name="custom_name", category="test")
        def my_func():
            pass
        
        assert my_func._mcp_name == "custom_name"
        assert my_func._mcp_category == "test"
    
    def test_decorator_uses_function_name(self):
        """Test that decorator uses function name when not specified."""
        @mcp_tool(category="math")
        def my_add_func():
            pass
        
        assert my_add_func._mcp_name == "my_add_func"
    
    def test_decorator_captures_docstring(self):
        """Test that decorator captures docstring as description."""
        @mcp_tool(name="test")
        def with_doc():
            """This is the description."""
            pass
        
        assert "This is the description" in with_doc._mcp_description
    
    def test_decorator_sets_tags(self):
        """Test that decorator sets tags."""
        @mcp_tool(name="test", tags=["tag1", "tag2"])
        def tagged_func():
            pass
        
        assert tagged_func._mcp_tags == ["tag1", "tag2"]
    
    def test_undecorated_function(self):
        """Test that undecorated functions don't have MCP attributes."""
        def plain_func():
            pass
        
        assert not hasattr(plain_func, "_mcp_tool")


class TestDiscoveredTool:
    """Test DiscoveredTool dataclass."""
    
    def test_tool_creation(self):
        """Test creating a DiscoveredTool."""
        def dummy_func():
            pass
        
        tool = DiscoveredTool(
            name="test",
            description="A test tool",
            function=dummy_func,
            module="test_module",
            category="test",
            tags=["utility"],
            parameters_schema={"type": "object"},
            returns_schema={"type": "string"},
        )
        
        assert tool.name == "test"
        assert tool.function == dummy_func
        assert tool.category == "test"


class TestToolDiscoveryInit:
    """Test ToolDiscovery initialization."""
    
    def test_uses_provided_registry(self, fresh_registry):
        """Test initialization with provided registry."""
        discovery = ToolDiscovery(registry=fresh_registry)
        assert discovery.registry is fresh_registry


class TestDiscoverModule:
    """Test discovering tools from modules."""
    
    def test_discover_finds_decorated_tools(self, discovery, mock_module_with_tools):
        """Test discovering tools from a module."""
        tools = discovery.discover_module("mock_test_module")
        
        tool_names = [t.name for t in tools]
        assert "echo" in tool_names
        assert "add_func" in tool_names
        assert "not_decorated" not in tool_names
    
    def test_discover_nonexistent_module(self, discovery):
        """Test discovering from non-existent module."""
        tools = discovery.discover_module("nonexistent.module.xyz")
        assert len(tools) == 0
    
    def test_discovered_tool_has_correct_metadata(self, discovery, mock_module_with_tools):
        """Test that discovered tools have correct metadata."""
        tools = discovery.discover_module("mock_test_module")
        
        echo_tool = next(t for t in tools if t.name == "echo")
        assert echo_tool.category == "test"
        assert "utility" in echo_tool.tags
    
    def test_discovered_tool_has_schema(self, discovery, mock_module_with_tools):
        """Test that discovered tools have parameter schemas."""
        tools = discovery.discover_module("mock_test_module")
        
        add_tool = next(t for t in tools if t.name == "add_func")
        assert "properties" in add_tool.parameters_schema
        assert "a" in add_tool.parameters_schema["properties"]


class TestDiscoverFile:
    """Test discovering tools from Python files."""
    
    def test_discover_from_file(self, discovery, tmp_path):
        """Test discovering tools from a Python file."""
        test_file = tmp_path / "test_tools.py"
        test_file.write_text('''
from mcp.discovery import mcp_tool

@mcp_tool(name="file_tool", category="file_ops", tags=["io"])
def file_tool(path: str) -> dict:
    """Process a file."""
    return {"path": path}
''')
        
        tools = discovery.discover_file(test_file)
        
        assert len(tools) == 1
        assert tools[0].name == "file_tool"
        assert tools[0].category == "file_ops"
    
    def test_discover_from_nonexistent_file(self, discovery, tmp_path):
        """Test discovering from non-existent file."""
        tools = discovery.discover_file(tmp_path / "nonexistent.py")
        assert len(tools) == 0
    
    def test_discover_from_invalid_python(self, discovery, tmp_path):
        """Test discovering from invalid Python file."""
        test_file = tmp_path / "invalid.py"
        test_file.write_text("not valid python @#$%")
        
        tools = discovery.discover_file(test_file)
        assert len(tools) == 0


class TestSchemaBuilding:
    """Test JSON schema building from type hints."""
    
    def test_string_parameter(self, discovery):
        """Test string parameter schema."""
        def func(name: str) -> str:
            return name
        
        sig = inspect.signature(func)
        schema = discovery._build_parameters_schema(sig)
        
        assert schema["properties"]["name"]["type"] == "string"
    
    def test_int_parameter(self, discovery):
        """Test int parameter schema."""
        def func(count: int) -> int:
            return count
        
        sig = inspect.signature(func)
        schema = discovery._build_parameters_schema(sig)
        
        assert schema["properties"]["count"]["type"] == "number"
    
    def test_bool_parameter(self, discovery):
        """Test bool parameter schema."""
        def func(enabled: bool) -> bool:
            return enabled
        
        sig = inspect.signature(func)
        schema = discovery._build_parameters_schema(sig)
        
        assert schema["properties"]["enabled"]["type"] == "boolean"
    
    def test_required_parameters(self, discovery):
        """Test that required parameters are marked."""
        def func(required: str, optional: str = "default") -> str:
            return required
        
        sig = inspect.signature(func)
        schema = discovery._build_parameters_schema(sig)
        
        assert "required" in schema["required"]
        assert "optional" not in schema["required"]
    
    def test_default_values(self, discovery):
        """Test that default values are captured."""
        def func(name: str = "default") -> str:
            return name
        
        sig = inspect.signature(func)
        schema = discovery._build_parameters_schema(sig)
        
        assert schema["properties"]["name"]["default"] == "default"


class TestTypeToSchema:
    """Test type annotation to JSON schema conversion."""
    
    def test_str_annotation(self, discovery):
        """Test string annotation."""
        schema = discovery._type_to_schema(str)
        assert schema["type"] == "string"
    
    def test_int_annotation(self, discovery):
        """Test int annotation."""
        schema = discovery._type_to_schema(int)
        assert schema["type"] == "number"
    
    def test_optional_annotation(self, discovery):
        """Test Optional[T] annotation."""
        from typing import Optional
        schema = discovery._type_to_schema(Optional[str])
        assert schema["type"] == "string"


class TestAutoRegister:
    """Test auto-registration of discovered tools."""
    
    def test_auto_register_module(self, discovery, mock_module_with_tools, fresh_registry):
        """Test auto-registering tools from a module."""
        registered = discovery.auto_register("mock_test_module")
        
        assert "echo" in registered
        assert "add_func" in registered
        assert fresh_registry.get("echo") is not None
    
    def test_auto_register_skips_unresolved_functions(self, discovery, fresh_registry):
        """Test that tools without resolved functions are skipped."""
        # Add a discovered tool with no function
        discovery._discovered.append(DiscoveredTool(
            name="no_func",
            description="No function",
            function=None,  # type: ignore
            module="test",
            category="test",
            tags=[],
            parameters_schema={},
            returns_schema={},
        ))
        
        registered = discovery.auto_register("mock_test_module")
        assert "no_func" not in registered


class TestClearDiscovered:
    """Test clearing discovered tools cache."""
    
    def test_clear_discovered(self, discovery, mock_module_with_tools):
        """Test clearing discovered tools."""
        discovery.discover_module("mock_test_module")
        assert len(discovery.get_discovered()) > 0
        
        discovery.clear()
        assert len(discovery.get_discovered()) == 0
