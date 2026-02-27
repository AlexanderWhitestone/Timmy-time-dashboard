"""Tests for inter-agent delegation tools."""

import pytest
from unittest.mock import patch, MagicMock


def test_delegate_task_valid_agent():
    """Should be able to delegate to a valid agent."""
    from timmy.tools_delegation import delegate_task

    with patch("swarm.coordinator.coordinator") as mock_coordinator:
        mock_task = MagicMock()
        mock_task.task_id = "task_123"
        mock_coordinator.post_task.return_value = mock_task

        result = delegate_task("seer", "analyze this data")

        assert result["success"] is True
        assert result["task_id"] == "task_123"
        assert result["agent"] == "seer"


def test_delegate_task_invalid_agent():
    """Should return error for invalid agent."""
    from timmy.tools_delegation import delegate_task

    result = delegate_task("nonexistent", "do something")

    assert result["success"] is False
    assert "error" in result
    assert "Unknown agent" in result["error"]


def test_delegate_task_priority():
    """Should respect priority parameter."""
    from timmy.tools_delegation import delegate_task

    with patch("swarm.coordinator.coordinator") as mock_coordinator:
        mock_task = MagicMock()
        mock_task.task_id = "task_456"
        mock_coordinator.post_task.return_value = mock_task

        result = delegate_task("forge", "write code", priority="high")

        assert result["success"] is True
        mock_coordinator.post_task.assert_called_once()
        call_kwargs = mock_coordinator.post_task.call_args.kwargs
        assert call_kwargs.get("priority") == "high"


def test_list_swarm_agents():
    """Should list available swarm agents."""
    from timmy.tools_delegation import list_swarm_agents

    with patch("swarm.coordinator.coordinator") as mock_coordinator:
        mock_agent = MagicMock()
        mock_agent.name = "seer"
        mock_agent.status = "idle"
        mock_agent.capabilities = ["analysis"]
        mock_coordinator.list_swarm_agents.return_value = [mock_agent]

        result = list_swarm_agents()

        assert result["success"] is True
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "seer"
