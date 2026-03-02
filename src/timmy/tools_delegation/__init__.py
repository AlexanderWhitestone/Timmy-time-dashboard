"""Timmy's delegation tools — submit tasks and list agents.

Coordinator removed. Tasks go through the task_queue, agents are
looked up in the registry.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def delegate_task(agent_name: str, task_description: str, priority: str = "normal") -> dict[str, Any]:
    """Delegate a task to another agent via the task queue.

    Args:
        agent_name: Name of the agent to delegate to
        task_description: What you want the agent to do
        priority: Task priority - "low", "normal", "high"

    Returns:
        Dict with task_id, status, and message
    """
    valid_agents = ["seer", "forge", "echo", "helm", "quill", "mace"]
    agent_name = agent_name.lower().strip()

    if agent_name not in valid_agents:
        return {
            "success": False,
            "error": f"Unknown agent: {agent_name}. Valid agents: {', '.join(valid_agents)}",
            "task_id": None,
        }

    valid_priorities = ["low", "normal", "high"]
    if priority not in valid_priorities:
        priority = "normal"

    try:
        from swarm.task_queue.models import create_task

        task = create_task(
            title=f"[Delegated to {agent_name}] {task_description[:80]}",
            description=task_description,
            assigned_to=agent_name,
            created_by="timmy",
            priority=priority,
            task_type="task_request",
            requires_approval=False,
            auto_approve=True,
        )

        return {
            "success": True,
            "task_id": task.id,
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
    try:
        from swarm import registry

        agents = registry.list_agents()

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
