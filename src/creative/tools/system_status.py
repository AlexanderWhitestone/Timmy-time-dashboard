"""System status introspection tool for Timmy.

MCP-compliant tool that gives Timmy live access to his own system state:
task queue, agent roster, memory tiers, uptime, and service health.
"""

import json
import logging

from mcp.registry import register_tool
from mcp.schemas.base import create_tool_schema, RETURN_STRING

logger = logging.getLogger(__name__)


SYSTEM_STATUS_SCHEMA = create_tool_schema(
    name="system_status",
    description=(
        "Get live system status including task queue counts, agent roster, "
        "memory tier health, uptime, and service connectivity. "
        "Use this when asked about your status, what you're working on, "
        "agent health, or system metrics. Never guess — always call this tool."
    ),
    parameters={},
    required=[],
    returns=RETURN_STRING,
)


def system_status() -> str:
    """Return comprehensive live system status as formatted text.

    Returns:
        JSON-formatted string with system, task_queue, agents, memory sections.
    """
    try:
        from timmy.tools_intro import get_live_system_status

        status = get_live_system_status()
        return json.dumps(status, indent=2, default=str)
    except Exception as exc:
        logger.error("system_status tool failed: %s", exc)
        return json.dumps({"error": str(exc)})


# Register with MCP
register_tool(
    name="system_status",
    schema=SYSTEM_STATUS_SCHEMA,
    category="system",
)(system_status)
