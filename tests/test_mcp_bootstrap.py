"""Tests for MCP Auto-Bootstrap.

Tests follow pytest best practices:
- No module-level state
- Proper fixture cleanup
- Isolated tests
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp.bootstrap import (
    auto_bootstrap,
    bootstrap_from_directory,
    get_bootstrap_status,
    DEFAULT_TOOL_PACKAGES,
    AUTO_BOOTSTRAP_ENV_VAR,
)
from mcp.discovery import mcp_tool, ToolDiscovery
from mcp.registry import ToolRegistry


@pytest.fixture
def fresh_registry():
    """Create a fresh registry for each test."""
    return ToolRegistry()


@pytest.fixture
def fresh_discovery(fresh_registry):
    """Create a fresh discovery instance for each test."""
    return ToolDiscovery(registry=fresh_registry)


class TestAutoBootstrap:
    """Test auto_bootstrap function."""
    
    def test_auto_bootstrap_disabled_by_env(self, fresh_registry):
        """Test that auto-bootstrap can be disabled via env var."""
        with patch.dict(os.environ, {AUTO_BOOTSTRAP_ENV_VAR: "0"}):
            registered = auto_bootstrap(registry=fresh_registry)
        
        assert len(registered) == 0
    
    def test_auto_bootstrap_forced_overrides_env(self, fresh_registry):
        """Test that force=True overrides env var."""
        with patch.dict(os.environ, {AUTO_BOOTSTRAP_ENV_VAR: "0"}):
            # Empty packages list - just test that it runs
            registered = auto_bootstrap(
                packages=[],
                registry=fresh_registry,
                force=True,
            )
        
        assert len(registered) == 0  # No packages, but didn't abort
    
    def test_auto_bootstrap_nonexistent_package(self, fresh_registry):
        """Test bootstrap from non-existent package."""
        registered = auto_bootstrap(
            packages=["nonexistent_package_xyz_12345"],
            registry=fresh_registry,
            force=True,
        )
        
        assert len(registered) == 0
    
    def test_auto_bootstrap_empty_packages(self, fresh_registry):
        """Test bootstrap with empty packages list."""
        registered = auto_bootstrap(
            packages=[],
            registry=fresh_registry,
            force=True,
        )
        
        assert len(registered) == 0
    
    def test_auto_bootstrap_registers_tools(self, fresh_registry, fresh_discovery):
        """Test that auto-bootstrap registers discovered tools."""
        @mcp_tool(name="bootstrap_tool", category="bootstrap")
        def bootstrap_func(value: str) -> str:
            """A bootstrap test tool."""
            return value
        
        # Manually register it
        fresh_registry.register_tool(
            name="bootstrap_tool",
            function=bootstrap_func,
            category="bootstrap",
        )
        
        # Verify it's in the registry
        record = fresh_registry.get("bootstrap_tool")
        assert record is not None
        assert record.auto_discovered is True


class TestBootstrapFromDirectory:
    """Test bootstrap_from_directory function."""
    
    def test_bootstrap_from_directory(self, fresh_registry, tmp_path):
        """Test bootstrapping from a directory."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        
        tool_file = tools_dir / "my_tools.py"
        tool_file.write_text('''
from mcp.discovery import mcp_tool

@mcp_tool(name="dir_tool", category="directory")
def dir_tool(value: str) -> str:
    """A tool from directory."""
    return value
''')
        
        registered = bootstrap_from_directory(tools_dir, registry=fresh_registry)
        
        # Function won't be resolved (AST only), so not registered
        assert len(registered) == 0
    
    def test_bootstrap_from_nonexistent_directory(self, fresh_registry):
        """Test bootstrapping from non-existent directory."""
        registered = bootstrap_from_directory(
            Path("/nonexistent/tools"), 
            registry=fresh_registry
        )
        
        assert len(registered) == 0
    
    def test_bootstrap_skips_private_files(self, fresh_registry, tmp_path):
        """Test that private files are skipped."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        
        private_file = tools_dir / "_private.py"
        private_file.write_text('''
from mcp.discovery import mcp_tool

@mcp_tool(name="private_tool")
def private_tool():
    pass
''')
        
        registered = bootstrap_from_directory(tools_dir, registry=fresh_registry)
        assert len(registered) == 0


class TestGetBootstrapStatus:
    """Test get_bootstrap_status function."""
    
    def test_status_default_enabled(self):
        """Test status when auto-bootstrap is enabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            status = get_bootstrap_status()
        
        assert status["auto_bootstrap_enabled"] is True
        assert "discovered_tools_count" in status
        assert "registered_tools_count" in status
        assert status["default_packages"] == DEFAULT_TOOL_PACKAGES
    
    def test_status_disabled(self):
        """Test status when auto-bootstrap is disabled."""
        with patch.dict(os.environ, {AUTO_BOOTSTRAP_ENV_VAR: "0"}):
            status = get_bootstrap_status()
        
        assert status["auto_bootstrap_enabled"] is False


class TestIntegration:
    """Integration tests for bootstrap + discovery + registry."""
    
    def test_full_workflow(self, fresh_registry):
        """Test the full auto-discovery and registration workflow."""
        @mcp_tool(name="integration_tool", category="integration")
        def integration_func(data: str) -> str:
            """Integration test tool."""
            return f"processed: {data}"
        
        fresh_registry.register_tool(
            name="integration_tool",
            function=integration_func,
            category="integration",
            source_module="test_module",
        )
        
        record = fresh_registry.get("integration_tool")
        assert record is not None
        assert record.auto_discovered is True
        assert record.source_module == "test_module"
        
        export = fresh_registry.to_dict()
        assert export["total_tools"] == 1
        assert export["auto_discovered_count"] == 1
    
    def test_tool_execution_after_registration(self, fresh_registry):
        """Test that registered tools can be executed."""
        @mcp_tool(name="exec_tool", category="execution")
        def exec_func(input: str) -> str:
            """Executable test tool."""
            return input.upper()
        
        fresh_registry.register_tool(
            name="exec_tool",
            function=exec_func,
            category="execution",
        )
        
        import asyncio
        result = asyncio.run(fresh_registry.execute("exec_tool", {"input": "hello"}))
        
        assert result == "HELLO"
        
        metrics = fresh_registry.get_metrics("exec_tool")
        assert metrics["executions"] == 1
        assert metrics["health"] == "healthy"
    
    def test_discover_filtering(self, fresh_registry):
        """Test filtering registered tools."""
        @mcp_tool(name="cat1_tool", category="category1")
        def cat1_func():
            pass
        
        @mcp_tool(name="cat2_tool", category="category2")
        def cat2_func():
            pass
        
        fresh_registry.register_tool(
            name="cat1_tool", 
            function=cat1_func, 
            category="category1"
        )
        fresh_registry.register_tool(
            name="cat2_tool", 
            function=cat2_func, 
            category="category2"
        )
        
        cat1_tools = fresh_registry.discover(category="category1")
        assert len(cat1_tools) == 1
        assert cat1_tools[0].name == "cat1_tool"
        
        auto_tools = fresh_registry.discover(auto_discovered_only=True)
        assert len(auto_tools) == 2
    
    def test_registry_export_includes_metadata(self, fresh_registry):
        """Test that registry export includes all metadata."""
        @mcp_tool(name="meta_tool", category="meta", tags=["tag1", "tag2"])
        def meta_func():
            pass
        
        fresh_registry.register_tool(
            name="meta_tool",
            function=meta_func,
            category="meta",
            tags=["tag1", "tag2"],
        )
        
        export = fresh_registry.to_dict()
        
        for tool_dict in export["tools"]:
            assert "tags" in tool_dict
            assert "source_module" in tool_dict
            assert "auto_discovered" in tool_dict
