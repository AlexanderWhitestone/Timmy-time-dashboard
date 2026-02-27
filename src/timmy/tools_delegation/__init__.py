"""Inter-agent delegation tools for Timmy.

Allows Timmy to dispatch tasks to other swarm agents (Seer, Forge, Echo, etc.)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def delegate_task(
    agent_name: str, task_description: str, priority: str = "normal"
) -> dict[str, Any]:
    """Dispatch a task to another swarm agent.

    Args:
        agent_name: Name of the agent to delegate to (seer, forge, echo, helm, quill)
        task_description: What you want the agent to do
        priority: Task priority - "low", "normal", "high"

    Returns:
        Dict with task_id, status, and message
    """
    from swarm.coordinator import coordinator

    # Validate agent name
    valid_agents = ["seer", "forge", "echo", "helm", "quill", "mace"]
    agent_name = agent_name.lower().strip()

    if agent_name not in valid_agents:
        return {
            "success": False,
            "error": f"Unknown agent: {agent_name}. Valid agents: {', '.join(valid_agents)}",
            "task_id": None,
        }

    # Validate priority
    valid_priorities = ["low", "normal", "high"]
    if priority not in valid_priorities:
        priority = "normal"

    try:
        # Submit task to coordinator
        task = coordinator.post_task(
            description=task_description,
            assigned_agent=agent_name,
            priority=priority,
        )

        return {
            "success": True,
            "task_id": task.task_id,
            "agent": agent_name,
            "status": "submitted",
            "message": f"Task submitted to {agent_name}: {task_description[:100]}...",
        }

    except Exception as e:
        logger.error("Failed to delegate task to %s: %s", agent_name, e)
        return {
            "success": False,
            "error": str(e),
            "task_id": None,
        }


def list_swarm_agents() -> dict[str, Any]:
    """List all available swarm agents and their status.

    Returns:
        Dict with agent list and status
    """
    from swarm.coordinator import coordinator

    try:
        agents = coordinator.list_swarm_agents()

        return {
            "success": True,
            "agents": [
                {
                    "name": a.name,
                    "status": a.status,
                    "capabilities": a.capabilities,
                }
                for a in agents
            ],
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "agents": [],
        }
