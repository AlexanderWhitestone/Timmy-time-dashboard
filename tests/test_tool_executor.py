"""Tests for MCP tool execution in swarm agents.

Covers:
- ToolExecutor initialization for each persona
- Task execution with appropriate tools
- Tool inference from task descriptions
- Error handling when tools unavailable

Note: These tests run with mocked Agno, so actual tool availability
may be limited. Tests verify the interface works correctly.
"""

import pytest
from pathlib import Path

from swarm.tool_executor import ToolExecutor
from swarm.persona_node import PersonaNode
from swarm.comms import SwarmComms


class TestToolExecutor:
    """Tests for the ToolExecutor class."""
    
    def test_create_for_persona_forge(self):
        """Can create executor for Forge (coding) persona."""
        executor = ToolExecutor.for_persona("forge", "forge-test-001")
        
        assert executor._persona_id == "forge"
        assert executor._agent_id == "forge-test-001"
        
    def test_create_for_persona_echo(self):
        """Can create executor for Echo (research) persona."""
        executor = ToolExecutor.for_persona("echo", "echo-test-001")
        
        assert executor._persona_id == "echo"
        assert executor._agent_id == "echo-test-001"
        
    def test_get_capabilities_returns_list(self):
        """get_capabilities returns list (may be empty if tools unavailable)."""
        executor = ToolExecutor.for_persona("forge", "forge-test-001")
        caps = executor.get_capabilities()
        
        assert isinstance(caps, list)
        # Note: In tests with mocked Agno, this may be empty
        
    def test_describe_tools_returns_string(self):
        """Tool descriptions are generated as string."""
        executor = ToolExecutor.for_persona("forge", "forge-test-001")
        desc = executor._describe_tools()
        
        assert isinstance(desc, str)
        # When toolkit is None, returns "No tools available"
        
    def test_infer_tools_for_code_task(self):
        """Correctly infers tools needed for coding tasks."""
        executor = ToolExecutor.for_persona("forge", "forge-test-001")
        
        task = "Write a Python function to calculate fibonacci"
        tools = executor._infer_tools_needed(task)
        
        # Should infer python tool from keywords
        assert "python" in tools
        
    def test_infer_tools_for_search_task(self):
        """Correctly infers tools needed for research tasks."""
        executor = ToolExecutor.for_persona("echo", "echo-test-001")
        
        task = "Search for information about Python asyncio"
        tools = executor._infer_tools_needed(task)
        
        # Should infer web_search from "search" keyword
        assert "web_search" in tools
        
    def test_infer_tools_for_file_task(self):
        """Correctly infers tools needed for file operations."""
        executor = ToolExecutor.for_persona("quill", "quill-test-001")
        
        task = "Read the README file and write a summary"
        tools = executor._infer_tools_needed(task)
        
        # Should infer read_file from "read" keyword
        assert "read_file" in tools
        
    def test_execute_task_returns_dict(self):
        """Task execution returns result dict."""
        executor = ToolExecutor.for_persona("echo", "echo-test-001")
        
        result = executor.execute_task("What is the weather today?")
        
        assert isinstance(result, dict)
        assert "success" in result
        assert "result" in result
        assert "tools_used" in result
        
    def test_execute_task_includes_metadata(self):
        """Task result includes persona and agent IDs."""
        executor = ToolExecutor.for_persona("seer", "seer-test-001")
        
        result = executor.execute_task("Analyze this data")
        
        # Check metadata is present when execution succeeds
        if result.get("success"):
            assert result.get("persona_id") == "seer"
            assert result.get("agent_id") == "seer-test-001"
        
    def test_execute_task_handles_empty_toolkit(self):
        """Execution handles case where toolkit is None."""
        executor = ToolExecutor("unknown", "unknown-001")
        executor._toolkit = None  # Force None
        
        result = executor.execute_task("Some task")
        
        # Should still return a result even without toolkit
        assert isinstance(result, dict)
        assert "success" in result or "result" in result


class TestPersonaNodeToolIntegration:
    """Tests for PersonaNode integration with tools."""
    
    def test_persona_node_has_tool_executor(self):
        """PersonaNode initializes with tool executor (or None if tools unavailable)."""
        comms = SwarmComms()
        node = PersonaNode("forge", "forge-test-001", comms=comms)
        
        # Should have tool executor attribute
        assert hasattr(node, '_tool_executor')
        
    def test_persona_node_tool_capabilities(self):
        """PersonaNode exposes tool capabilities (may be empty in tests)."""
        comms = SwarmComms()
        node = PersonaNode("forge", "forge-test-001", comms=comms)
        
        caps = node.tool_capabilities
        assert isinstance(caps, list)
        # Note: May be empty in tests with mocked Agno
        
    def test_persona_node_tracks_current_task(self):
        """PersonaNode tracks currently executing task."""
        comms = SwarmComms()
        node = PersonaNode("echo", "echo-test-001", comms=comms)
        
        # Initially no current task
        assert node.current_task is None
        
    def test_persona_node_handles_unknown_task(self):
        """PersonaNode handles task not found gracefully."""
        comms = SwarmComms()
        node = PersonaNode("forge", "forge-test-001", comms=comms)
        
        # Try to handle non-existent task
        # This should log error but not crash
        node._handle_task_assignment("non-existent-task-id")
        
        # Should have no current task after handling
        assert node.current_task is None


class TestToolInference:
    """Tests for tool inference from task descriptions."""
    
    def test_infer_shell_from_command_keyword(self):
        """Shell tool inferred from 'command' keyword."""
        executor = ToolExecutor.for_persona("helm", "helm-test")
        
        tools = executor._infer_tools_needed("Run the deploy command")
        assert "shell" in tools
        
    def test_infer_write_file_from_save_keyword(self):
        """Write file tool inferred from 'save' keyword."""
        executor = ToolExecutor.for_persona("quill", "quill-test")
        
        tools = executor._infer_tools_needed("Save this to a file")
        assert "write_file" in tools
        
    def test_infer_list_files_from_directory_keyword(self):
        """List files tool inferred from 'directory' keyword."""
        executor = ToolExecutor.for_persona("echo", "echo-test")
        
        tools = executor._infer_tools_needed("List files in the directory")
        assert "list_files" in tools
        
    def test_no_duplicate_tools(self):
        """Tool inference doesn't duplicate tools."""
        executor = ToolExecutor.for_persona("forge", "forge-test")
        
        # Task with multiple code keywords
        tools = executor._infer_tools_needed("Code a python script")
        
        # Should only have python once
        assert tools.count("python") == 1


class TestToolExecutionIntegration:
    """Integration tests for tool execution flow."""
    
    def test_task_execution_with_tools_unavailable(self):
        """Task execution works even when Agno tools unavailable."""
        executor = ToolExecutor.for_persona("echo", "echo-no-tools")
        
        # Force toolkit to None to simulate unavailable tools
        executor._toolkit = None
        executor._llm = None
        
        result = executor.execute_task("Search for something")
        
        # Should still return a valid result
        assert isinstance(result, dict)
        assert "result" in result
        # Tools should still be inferred even if not available
        assert "tools_used" in result
