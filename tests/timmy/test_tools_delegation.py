"""Tests for timmy.tools_delegation — delegate_task and list_swarm_agents."""

from unittest.mock import patch

from timmy.tools_delegation import delegate_task, list_swarm_agents


class TestDelegateTask:
    def test_unknown_agent_returns_error(self):
        result = delegate_task("nonexistent", "do something")
        assert result["success"] is False
        assert "Unknown agent" in result["error"]
        assert result["task_id"] is None

    def test_valid_agent_names_normalised(self):
        # Should still fail at import (no swarm module), but agent name is accepted
        result = delegate_task("  Seer  ", "think about it")
        # The swarm import will fail, so success=False but error is about import, not agent name
        assert "Unknown agent" not in result.get("error", "")

    def test_invalid_priority_defaults_to_normal(self):
        # Even with bad priority, delegate_task should not crash
        result = delegate_task("forge", "build", priority="ultra")
        assert isinstance(result, dict)

    def test_all_valid_agents_accepted(self):
        valid_agents = ["seer", "forge", "echo", "helm", "quill"]
        for agent in valid_agents:
            result = delegate_task(agent, "test task")
            assert "Unknown agent" not in result.get("error", ""), f"{agent} rejected"

    def test_mace_no_longer_valid(self):
        result = delegate_task("mace", "run security scan")
        assert result["success"] is False
        assert "Unknown agent" in result["error"]


class TestListSwarmAgents:
    def test_returns_agents_from_personas(self):
        result = list_swarm_agents()
        assert result["success"] is True
        assert len(result["agents"]) > 0
        agent_names = [a["name"] for a in result["agents"]]
        assert "Seer" in agent_names
        assert "Forge" in agent_names
