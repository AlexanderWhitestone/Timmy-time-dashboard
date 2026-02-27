"""Functional tests for timmy.tools — tool tracking, persona toolkits, catalog.

Covers tool usage statistics, persona-to-toolkit mapping, catalog generation,
and graceful degradation when Agno is unavailable.
"""

from unittest.mock import patch, MagicMock

import pytest

from timmy.tools import (
    _TOOL_USAGE,
    _track_tool_usage,
    get_tool_stats,
    get_tools_for_persona,
    get_all_available_tools,
    PERSONA_TOOLKITS,
)


@pytest.fixture(autouse=True)
def clear_usage():
    """Clear tool usage tracking between tests."""
    _TOOL_USAGE.clear()
    yield
    _TOOL_USAGE.clear()


# ── Tool usage tracking ──────────────────────────────────────────────────────


class TestToolTracking:
    def test_track_creates_agent_entry(self):
        _track_tool_usage("agent-1", "web_search", success=True)
        assert "agent-1" in _TOOL_USAGE
        assert len(_TOOL_USAGE["agent-1"]) == 1

    def test_track_records_metadata(self):
        _track_tool_usage("agent-1", "shell", success=False)
        entry = _TOOL_USAGE["agent-1"][0]
        assert entry["tool"] == "shell"
        assert entry["success"] is False
        assert "timestamp" in entry

    def test_track_multiple_calls(self):
        _track_tool_usage("a1", "search")
        _track_tool_usage("a1", "read")
        _track_tool_usage("a1", "search")
        assert len(_TOOL_USAGE["a1"]) == 3

    def test_track_multiple_agents(self):
        _track_tool_usage("a1", "search")
        _track_tool_usage("a2", "shell")
        assert len(_TOOL_USAGE) == 2


class TestGetToolStats:
    def test_stats_for_specific_agent(self):
        _track_tool_usage("a1", "search")
        _track_tool_usage("a1", "read")
        _track_tool_usage("a1", "search")
        stats = get_tool_stats("a1")
        assert stats["agent_id"] == "a1"
        assert stats["total_calls"] == 3
        assert set(stats["tools_used"]) == {"search", "read"}
        assert len(stats["recent_calls"]) == 3

    def test_stats_for_unknown_agent(self):
        stats = get_tool_stats("nonexistent")
        assert stats["total_calls"] == 0
        assert stats["tools_used"] == []
        assert stats["recent_calls"] == []

    def test_stats_recent_capped_at_10(self):
        for i in range(15):
            _track_tool_usage("a1", f"tool_{i}")
        stats = get_tool_stats("a1")
        assert len(stats["recent_calls"]) == 10

    def test_stats_all_agents(self):
        _track_tool_usage("a1", "search")
        _track_tool_usage("a2", "shell")
        _track_tool_usage("a2", "read")
        stats = get_tool_stats()
        assert "a1" in stats
        assert "a2" in stats
        assert stats["a1"]["total_calls"] == 1
        assert stats["a2"]["total_calls"] == 2

    def test_stats_empty(self):
        stats = get_tool_stats()
        assert stats == {}


# ── Persona toolkit mapping ──────────────────────────────────────────────────


class TestPersonaToolkits:
    def test_all_expected_personas_present(self):
        expected = {"echo", "mace", "helm", "seer", "forge", "quill", "pixel", "lyra", "reel"}
        assert set(PERSONA_TOOLKITS.keys()) == expected

    def test_get_tools_for_known_persona_raises_without_agno(self):
        """Agno is mocked but not a real package, so create_*_tools raises ImportError."""
        with pytest.raises(ImportError, match="Agno tools not available"):
            get_tools_for_persona("echo")

    def test_get_tools_for_unknown_persona(self):
        result = get_tools_for_persona("nonexistent")
        assert result is None

    def test_creative_personas_return_none(self):
        """Creative personas (pixel, lyra, reel) use stub toolkits that
        return None when Agno is unavailable."""
        for persona_id in ("pixel", "lyra", "reel"):
            result = get_tools_for_persona(persona_id)
            assert result is None


# ── Tool catalog ─────────────────────────────────────────────────────────────


class TestToolCatalog:
    def test_catalog_contains_base_tools(self):
        catalog = get_all_available_tools()
        base_tools = {"web_search", "shell", "python", "read_file", "write_file", "list_files"}
        for tool_id in base_tools:
            assert tool_id in catalog, f"Missing base tool: {tool_id}"

    def test_catalog_tool_structure(self):
        catalog = get_all_available_tools()
        for tool_id, info in catalog.items():
            assert "name" in info, f"{tool_id} missing 'name'"
            assert "description" in info, f"{tool_id} missing 'description'"
            assert "available_in" in info, f"{tool_id} missing 'available_in'"
            assert isinstance(info["available_in"], list)

    def test_catalog_timmy_has_all_base_tools(self):
        catalog = get_all_available_tools()
        base_tools = {"web_search", "shell", "python", "read_file", "write_file", "list_files"}
        for tool_id in base_tools:
            assert "timmy" in catalog[tool_id]["available_in"], (
                f"Timmy missing tool: {tool_id}"
            )

    def test_catalog_echo_research_tools(self):
        catalog = get_all_available_tools()
        assert "echo" in catalog["web_search"]["available_in"]
        assert "echo" in catalog["read_file"]["available_in"]
        # Echo should NOT have shell
        assert "echo" not in catalog["shell"]["available_in"]

    def test_catalog_forge_code_tools(self):
        catalog = get_all_available_tools()
        assert "forge" in catalog["shell"]["available_in"]
        assert "forge" in catalog["python"]["available_in"]
        assert "forge" in catalog["write_file"]["available_in"]

    def test_catalog_includes_git_tools(self):
        catalog = get_all_available_tools()
        git_tools = [k for k in catalog if "git" in k.lower()]
        # Should have some git tools from tools.git_tools
        assert len(git_tools) > 0

    def test_catalog_includes_creative_tools(self):
        catalog = get_all_available_tools()
        # Should pick up image, music, video catalogs
        all_keys = list(catalog.keys())
        assert len(all_keys) > 6  # more than just base tools
