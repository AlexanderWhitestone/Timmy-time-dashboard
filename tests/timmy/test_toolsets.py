"""Tests for the simplified toolset-based agent system.

TDD: The multi-agent system is collapsed into toolsets that the main
Timmy agent uses directly, eliminating the need for Helm routing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestToolsets:
    """Validate that agent capabilities are exposed as toolsets."""

    def test_get_toolsets_returns_dict(self):
        """get_toolsets should return a dict of capability -> functions."""
        from timmy.agents.toolsets import get_toolsets
        toolsets = get_toolsets()
        assert isinstance(toolsets, dict)

    def test_toolsets_has_research(self):
        """Toolsets should include research capability (was Seer)."""
        from timmy.agents.toolsets import get_toolsets
        toolsets = get_toolsets()
        assert "research" in toolsets

    def test_toolsets_has_code(self):
        """Toolsets should include code capability (was Forge)."""
        from timmy.agents.toolsets import get_toolsets
        toolsets = get_toolsets()
        assert "code" in toolsets

    def test_toolsets_has_writing(self):
        """Toolsets should include writing capability (was Quill)."""
        from timmy.agents.toolsets import get_toolsets
        toolsets = get_toolsets()
        assert "writing" in toolsets

    def test_toolsets_has_memory(self):
        """Toolsets should include memory capability (was Echo)."""
        from timmy.agents.toolsets import get_toolsets
        toolsets = get_toolsets()
        assert "memory" in toolsets

    def test_each_toolset_has_description(self):
        """Each toolset should have a description string."""
        from timmy.agents.toolsets import get_toolsets
        toolsets = get_toolsets()
        for name, toolset in toolsets.items():
            assert "description" in toolset, f"Toolset '{name}' missing description"
            assert isinstance(toolset["description"], str)

    def test_each_toolset_has_tools_list(self):
        """Each toolset should have a tools list."""
        from timmy.agents.toolsets import get_toolsets
        toolsets = get_toolsets()
        for name, toolset in toolsets.items():
            assert "tools" in toolset, f"Toolset '{name}' missing tools"
            assert isinstance(toolset["tools"], list)


class TestTimmyDirect:
    """Validate Timmy handles requests directly without Helm routing."""

    def test_classify_request_simple(self):
        """Simple requests should be classified as 'direct'."""
        from timmy.agents.toolsets import classify_request
        assert classify_request("hello") == "direct"
        assert classify_request("who are you?") == "direct"

    def test_classify_request_memory(self):
        """Memory-related requests should be classified as 'memory'."""
        from timmy.agents.toolsets import classify_request
        assert classify_request("what did we discuss yesterday?") == "memory"
        assert classify_request("remember that I like dark mode") == "memory"

    def test_classify_request_research(self):
        """Research requests should be classified as 'research'."""
        from timmy.agents.toolsets import classify_request
        assert classify_request("search for Bitcoin price info") == "research"

    def test_classify_request_code(self):
        """Code requests should be classified as 'code'."""
        from timmy.agents.toolsets import classify_request
        assert classify_request("write a Python function to sort a list") == "code"

    def test_classify_request_default(self):
        """Unmatched requests should default to 'direct'."""
        from timmy.agents.toolsets import classify_request
        assert classify_request("tell me about sovereignty") == "direct"
