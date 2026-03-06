"""Tests for timmy.agents.timmy — orchestrator, personas, context building."""

import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Ensure mcp.registry stub with tool_registry exists before importing agents
if "mcp" not in sys.modules:
    _mock_mcp = MagicMock()
    _mock_registry_mod = MagicMock()
    _mock_tool_reg = MagicMock()
    _mock_tool_reg.get_handler.return_value = None
    _mock_registry_mod.tool_registry = _mock_tool_reg
    sys.modules["mcp"] = _mock_mcp
    sys.modules["mcp.registry"] = _mock_registry_mod

from timmy.agents.timmy import (
    _load_hands_async,
    build_timmy_context_sync,
    build_timmy_context_async,
    format_timmy_prompt,
    TimmyOrchestrator,
    create_timmy_swarm,
    _PERSONAS,
    ORCHESTRATOR_PROMPT_BASE,
)


class TestLoadHandsAsync:
    """Test _load_hands_async."""

    async def test_returns_empty_list(self):
        result = await _load_hands_async()
        assert result == []


class TestBuildContext:
    """Test context building functions."""

    @patch("timmy.agents.timmy.settings")
    def test_build_context_sync_graceful_failures(self, mock_settings):
        mock_settings.repo_root = "/nonexistent"
        ctx = build_timmy_context_sync()

        assert "timestamp" in ctx
        assert isinstance(ctx["agents"], list)
        assert isinstance(ctx["hands"], list)
        # Git log should fall back gracefully
        assert isinstance(ctx["git_log"], str)
        # Memory should fall back gracefully
        assert isinstance(ctx["memory"], str)

    @patch("timmy.agents.timmy.settings")
    async def test_build_context_async(self, mock_settings):
        mock_settings.repo_root = "/nonexistent"
        ctx = await build_timmy_context_async()
        assert ctx["hands"] == []

    @patch("timmy.agents.timmy.settings")
    def test_build_context_reads_memory_file(self, mock_settings, tmp_path):
        memory_file = tmp_path / "MEMORY.md"
        memory_file.write_text("# Important memories\nRemember this.")
        mock_settings.repo_root = str(tmp_path)

        ctx = build_timmy_context_sync()
        assert "Important memories" in ctx["memory"]


class TestFormatPrompt:
    """Test format_timmy_prompt."""

    def test_inserts_context_block(self):
        base = "Line one.\nLine two."
        ctx = {
            "timestamp": "2026-03-06T00:00:00Z",
            "repo_root": "/home/user/project",
            "git_log": "abc123 initial commit",
            "agents": [],
            "hands": [],
            "memory": "some memory",
        }
        result = format_timmy_prompt(base, ctx)
        assert "Line one." in result
        assert "Line two." in result
        assert "abc123 initial commit" in result
        assert "some memory" in result

    def test_agents_list_formatted(self):
        ctx = {
            "timestamp": "now",
            "repo_root": "/tmp",
            "git_log": "",
            "agents": [
                {"name": "Forge", "capabilities": "code", "status": "ready"},
                {"name": "Seer", "capabilities": "research", "status": "ready"},
            ],
            "hands": [],
            "memory": "",
        }
        result = format_timmy_prompt("Base.", ctx)
        assert "Forge" in result
        assert "Seer" in result

    def test_hands_list_formatted(self):
        ctx = {
            "timestamp": "now",
            "repo_root": "/tmp",
            "git_log": "",
            "agents": [],
            "hands": [
                {"name": "backup", "schedule": "daily", "enabled": True},
            ],
            "memory": "",
        }
        result = format_timmy_prompt("Base.", ctx)
        assert "backup" in result
        assert "enabled" in result

    def test_repo_root_placeholder_replaced(self):
        ctx = {
            "timestamp": "now",
            "repo_root": "/my/repo",
            "git_log": "",
            "agents": [],
            "hands": [],
            "memory": "",
        }
        result = format_timmy_prompt("Root is {REPO_ROOT}.", ctx)
        assert "/my/repo" in result
        assert "{REPO_ROOT}" not in result


class TestExtractAgent:
    """Test TimmyOrchestrator._extract_agent static method."""

    def test_extracts_known_agents(self):
        assert TimmyOrchestrator._extract_agent("Primary Agent: Seer") == "seer"
        assert TimmyOrchestrator._extract_agent("Use Forge for this") == "forge"
        assert TimmyOrchestrator._extract_agent("Route to quill") == "quill"
        assert TimmyOrchestrator._extract_agent("echo can recall") == "echo"
        assert TimmyOrchestrator._extract_agent("helm decides") == "helm"

    def test_defaults_to_orchestrator(self):
        assert TimmyOrchestrator._extract_agent("no agent mentioned") == "orchestrator"

    def test_case_insensitive(self):
        assert TimmyOrchestrator._extract_agent("Use FORGE") == "forge"


class TestTimmyOrchestrator:
    """Test TimmyOrchestrator init and methods."""

    @patch("timmy.agents.timmy.settings")
    def test_init(self, mock_settings):
        mock_settings.repo_root = "/tmp"
        mock_settings.ollama_model = "test"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.telemetry_enabled = False

        orch = TimmyOrchestrator()
        assert orch.agent_id == "orchestrator"
        assert orch.name == "Orchestrator"
        assert orch.sub_agents == {}
        assert orch._session_initialized is False

    @patch("timmy.agents.timmy.settings")
    def test_register_sub_agent(self, mock_settings):
        mock_settings.repo_root = "/tmp"
        mock_settings.ollama_model = "test"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.telemetry_enabled = False

        orch = TimmyOrchestrator()

        from timmy.agents.base import SubAgent
        agent = SubAgent(
            agent_id="test-agent",
            name="Test",
            role="test",
            system_prompt="You are a test agent.",
        )
        orch.register_sub_agent(agent)
        assert "test-agent" in orch.sub_agents

    @patch("timmy.agents.timmy.settings")
    def test_get_swarm_status(self, mock_settings):
        mock_settings.repo_root = "/tmp"
        mock_settings.ollama_model = "test"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.telemetry_enabled = False

        orch = TimmyOrchestrator()
        status = orch.get_swarm_status()
        assert "orchestrator" in status
        assert status["total_agents"] == 1

    @patch("timmy.agents.timmy.settings")
    def test_get_enhanced_system_prompt_with_attr(self, mock_settings):
        mock_settings.repo_root = "/tmp"
        mock_settings.ollama_model = "test"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.telemetry_enabled = False

        orch = TimmyOrchestrator()
        # BaseAgent doesn't store system_prompt as attr; set it manually
        orch.system_prompt = "Test prompt.\nWith context."
        prompt = orch._get_enhanced_system_prompt()
        assert isinstance(prompt, str)
        assert "Test prompt." in prompt


class TestCreateTimmySwarm:
    """Test create_timmy_swarm factory."""

    @patch("timmy.agents.timmy.settings")
    def test_creates_all_personas(self, mock_settings):
        mock_settings.repo_root = "/tmp"
        mock_settings.ollama_model = "test"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.telemetry_enabled = False

        swarm = create_timmy_swarm()
        assert len(swarm.sub_agents) == len(_PERSONAS)
        assert "seer" in swarm.sub_agents
        assert "forge" in swarm.sub_agents
        assert "quill" in swarm.sub_agents
        assert "echo" in swarm.sub_agents
        assert "helm" in swarm.sub_agents


class TestPersonas:
    """Test persona definitions."""

    def test_all_personas_have_required_fields(self):
        required = {"agent_id", "name", "role", "system_prompt"}
        for persona in _PERSONAS:
            assert required.issubset(persona.keys()), f"Missing fields in {persona['name']}"

    def test_persona_ids_unique(self):
        ids = [p["agent_id"] for p in _PERSONAS]
        assert len(ids) == len(set(ids))

    def test_five_personas(self):
        assert len(_PERSONAS) == 5


class TestOrchestratorPrompt:
    """Test the ORCHESTRATOR_PROMPT_BASE constant."""

    def test_contains_hard_rules(self):
        assert "NEVER fabricate" in ORCHESTRATOR_PROMPT_BASE
        assert "do not know" in ORCHESTRATOR_PROMPT_BASE.lower()

    def test_contains_repo_root_placeholder(self):
        assert "{REPO_ROOT}" in ORCHESTRATOR_PROMPT_BASE
