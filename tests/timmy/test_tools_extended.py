"""Extended tests for timmy.tools — covers tool tracking, stats, and create_* functions."""

import pytest
from unittest.mock import patch, MagicMock

from timmy.tools import (
    _track_tool_usage,
    get_tool_stats,
    calculator,
    _TOOL_USAGE,
    ToolStats,
    AgentTools,
    PersonaTools,
    create_aider_tool,
)


class TestToolTracking:
    """Test _track_tool_usage and get_tool_stats."""

    def setup_method(self):
        _TOOL_USAGE.clear()

    def test_track_tool_usage(self):
        _track_tool_usage("agent-1", "web_search")
        assert "agent-1" in _TOOL_USAGE
        assert len(_TOOL_USAGE["agent-1"]) == 1
        assert _TOOL_USAGE["agent-1"][0]["tool"] == "web_search"
        assert _TOOL_USAGE["agent-1"][0]["success"] is True

    def test_track_multiple_calls(self):
        _track_tool_usage("agent-1", "tool_a")
        _track_tool_usage("agent-1", "tool_b")
        _track_tool_usage("agent-1", "tool_a", success=False)
        assert len(_TOOL_USAGE["agent-1"]) == 3

    def test_get_tool_stats_specific_agent(self):
        _track_tool_usage("agent-x", "read_file")
        _track_tool_usage("agent-x", "write_file")

        stats = get_tool_stats("agent-x")
        assert stats["agent_id"] == "agent-x"
        assert stats["total_calls"] == 2
        assert set(stats["tools_used"]) == {"read_file", "write_file"}

    def test_get_tool_stats_no_data(self):
        stats = get_tool_stats("nonexistent")
        assert stats["total_calls"] == 0
        assert stats["tools_used"] == []

    def test_get_tool_stats_all_agents(self):
        _track_tool_usage("a1", "t1")
        _track_tool_usage("a2", "t2")
        _track_tool_usage("a2", "t3")

        stats = get_tool_stats()
        assert "a1" in stats
        assert stats["a1"]["total_calls"] == 1
        assert stats["a2"]["total_calls"] == 2

    def test_recent_calls_capped_at_10(self):
        for i in range(15):
            _track_tool_usage("agent-y", f"tool_{i}")

        stats = get_tool_stats("agent-y")
        assert len(stats["recent_calls"]) == 10

    def teardown_method(self):
        _TOOL_USAGE.clear()


class TestToolStats:
    """Test ToolStats dataclass."""

    def test_defaults(self):
        ts = ToolStats(tool_name="calc")
        assert ts.call_count == 0
        assert ts.last_used is None
        assert ts.errors == 0


class TestAgentTools:
    """Test AgentTools dataclass and backward compat alias."""

    def test_persona_tools_alias(self):
        assert PersonaTools is AgentTools


class TestCalculatorExtended:
    """Extended tests for the calculator tool."""

    def test_division(self):
        assert calculator("10 / 3") == str(10 / 3)

    def test_exponents(self):
        assert calculator("2**10") == "1024"

    def test_math_functions(self):
        import math
        assert calculator("math.sqrt(144)") == "12.0"
        assert calculator("math.pi") == str(math.pi)
        assert calculator("math.log(100, 10)") == str(math.log(100, 10))

    def test_builtins_blocked(self):
        result = calculator("__import__('os').system('ls')")
        assert "Error" in result

    def test_abs_allowed(self):
        assert calculator("abs(-5)") == "5"

    def test_round_allowed(self):
        assert calculator("round(3.14159, 2)") == "3.14"

    def test_min_max_allowed(self):
        assert calculator("min(1, 2, 3)") == "1"
        assert calculator("max(1, 2, 3)") == "3"

    def test_invalid_expression(self):
        result = calculator("not valid python")
        assert "Error" in result

    def test_division_by_zero(self):
        result = calculator("1/0")
        assert "Error" in result


class TestCreateToolFunctions:
    """Test that create_*_tools functions check availability."""

    def test_create_research_tools_no_agno(self):
        with patch("timmy.tools._AGNO_TOOLS_AVAILABLE", False):
            with patch("timmy.tools._ImportError", ImportError("no agno")):
                with pytest.raises(ImportError):
                    from timmy.tools import create_research_tools
                    create_research_tools()

    def test_create_code_tools_no_agno(self):
        with patch("timmy.tools._AGNO_TOOLS_AVAILABLE", False):
            with patch("timmy.tools._ImportError", ImportError("no agno")):
                with pytest.raises(ImportError):
                    from timmy.tools import create_code_tools
                    create_code_tools()

    def test_create_data_tools_no_agno(self):
        with patch("timmy.tools._AGNO_TOOLS_AVAILABLE", False):
            with patch("timmy.tools._ImportError", ImportError("no agno")):
                with pytest.raises(ImportError):
                    from timmy.tools import create_data_tools
                    create_data_tools()

    def test_create_writing_tools_no_agno(self):
        with patch("timmy.tools._AGNO_TOOLS_AVAILABLE", False):
            with patch("timmy.tools._ImportError", ImportError("no agno")):
                with pytest.raises(ImportError):
                    from timmy.tools import create_writing_tools
                    create_writing_tools()


class TestAiderTool:
    """Test AiderTool created by create_aider_tool."""

    def test_create_aider_tool(self, tmp_path):
        tool = create_aider_tool(tmp_path)
        assert hasattr(tool, "run_aider")
        assert tool.base_dir == tmp_path

    @patch("subprocess.run")
    def test_aider_success(self, mock_run, tmp_path):
        tool = create_aider_tool(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stdout="Changes applied")
        result = tool.run_aider("add fibonacci function")
        assert "Changes applied" in result

    @patch("subprocess.run")
    def test_aider_error(self, mock_run, tmp_path):
        tool = create_aider_tool(tmp_path)
        mock_run.return_value = MagicMock(returncode=1, stderr="something broke")
        result = tool.run_aider("bad prompt")
        assert "error" in result.lower()

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_aider_not_installed(self, mock_run, tmp_path):
        tool = create_aider_tool(tmp_path)
        result = tool.run_aider("test")
        assert "not installed" in result.lower()

    @patch("subprocess.run")
    def test_aider_timeout(self, mock_run, tmp_path):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="aider", timeout=120)
        tool = create_aider_tool(tmp_path)
        result = tool.run_aider("slow task")
        assert "timed out" in result.lower()
