"""Timmy's delegation tools — submit tasks and list agents.

Delegation uses the orchestrator's sub-agent system.  The old swarm
task-queue was removed; delegation now records intent and returns the
target agent information.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Agents available in the current orchestrator architecture
_VALID_AGENTS: dict[str, str] = {
    "seer": "research",
    "forge": "code",
    "echo": "memory",
    "helm": "routing",
    "quill": "writing",
}


def delegate_task(agent_name: str, task_description: str, priority: str = "normal") -> dict[str, Any]:
    """Record a delegation intent to another agent.

    Args:
        agent_name: Name of the agent to delegate to
        task_description: What you want the agent to do
        priority: Task priority - "low", "normal", "high"

    Returns:
        Dict with agent, status, and message
    """
    agent_name = agent_name.lower().strip()

    if agent_name not in _VALID_AGENTS:
        return {
            "success": False,
            "error": f"Unknown agent: {agent_name}. Valid agents: {', '.join(sorted(_VALID_AGENTS))}",
            "task_id": None,
        }

    valid_priorities = ["low", "normal", "high"]
    if priority not in valid_priorities:
        priority = "normal"

    logger.info("Delegation intent: %s → %s (priority=%s)", agent_name, task_description[:80], priority)

    return {
        "success": True,
        "task_id": None,
        "agent": agent_name,
        "role": _VALID_AGENTS[agent_name],
        "status": "noted",
        "message": f"Delegation to {agent_name} ({_VALID_AGENTS[agent_name]}): {task_description[:100]}",
    }


def list_swarm_agents() -> dict[str, Any]:
    """List all available sub-agents and their roles.

    Returns:
        Dict with agent list
    """
    try:
        from timmy.agents.timmy import _PERSONAS

        return {
            "success": True,
            "agents": [
                {
                    "name": p["name"],
                    "id": p["agent_id"],
                    "role": p.get("role", ""),
                    "status": "available",
                    "capabilities": ", ".join(p.get("tools", [])),
                }
                for p in _PERSONAS
            ],
        }
    except Exception as e:
        logger.debug("Agent list unavailable: %s", e)
        return {
            "success": False,
            "error": str(e),
            "agents": [],
        }
