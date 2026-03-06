"""Register Shell and Git Hands as MCP tools in Timmy's tool registry.

Shell and Git hands are local execution hands (no HTTP sidecar).
They provide Timmy with the ability to run shell commands and
perform git operations directly.

Call ``register_hand_tools()`` during app startup to populate
the tool registry.
"""

import logging
from typing import Any

from infrastructure.hands.shell import shell_hand
from infrastructure.hands.git import git_hand

try:
    from mcp.schemas.base import create_tool_schema
except ImportError:
    def create_tool_schema(**kwargs):
        return kwargs

logger = logging.getLogger(__name__)

# ── Tool schemas ─────────────────────────────────────────────────────────────

_HAND_SCHEMAS: dict[str, dict] = {
    "shell": create_tool_schema(
        name="hand_shell",
        description=(
            "Execute a shell command in a sandboxed environment. "
            "Commands are validated against an allow-list. "
            "Returns stdout, stderr, and exit code."
        ),
        parameters={
            "command": {
                "type": "string",
                "description": "Shell command to execute (must match allow-list)",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 60)",
                "default": 60,
            },
        },
        required=["command"],
    ),
    "git": create_tool_schema(
        name="hand_git",
        description=(
            "Execute a git operation in the project repository. "
            "Supports status, log, diff, add, commit, push, pull, "
            "clone, and branch operations. Destructive operations "
            "(force-push, hard reset) require explicit confirmation."
        ),
        parameters={
            "args": {
                "type": "string",
                "description": "Git arguments (e.g. 'status', 'log --oneline -5')",
            },
            "allow_destructive": {
                "type": "boolean",
                "description": "Allow destructive operations (default false)",
                "default": False,
            },
        },
        required=["args"],
    ),
}

# Map personas to local hands they should have access to
PERSONA_LOCAL_HAND_MAP: dict[str, list[str]] = {
    "forge": ["shell", "git"],
    "helm": ["shell", "git"],
    "echo": ["git"],
    "seer": ["shell"],
    "quill": [],
    "pixel": [],
    "lyra": [],
    "reel": [],
}


# ── Handlers ─────────────────────────────────────────────────────────────────

async def _handle_shell(**kwargs: Any) -> str:
    """Handler for the shell MCP tool."""
    command = kwargs.get("command", "")
    timeout = kwargs.get("timeout")
    result = await shell_hand.run(command, timeout=timeout)
    if result.success:
        return result.stdout or "(no output)"
    return f"[Shell error] exit={result.exit_code} {result.error or result.stderr}"


async def _handle_git(**kwargs: Any) -> str:
    """Handler for the git MCP tool."""
    args = kwargs.get("args", "")
    allow_destructive = kwargs.get("allow_destructive", False)
    result = await git_hand.run(args, allow_destructive=allow_destructive)
    if result.success:
        return result.output or "(no output)"
    if result.requires_confirmation:
        return f"[Git blocked] {result.error}"
    return f"[Git error] {result.error or result.output}"


_HANDLERS = {
    "shell": _handle_shell,
    "git": _handle_git,
}


def register_hand_tools() -> int:
    """Register Shell and Git hands as MCP tools.

    Returns the number of tools registered.
    """
    try:
        from mcp.registry import tool_registry
    except ImportError:
        logger.warning("MCP registry not available — skipping hand tool registration")
        return 0

    count = 0
    for hand_name, schema in _HAND_SCHEMAS.items():
        tool_name = f"hand_{hand_name}"
        handler = _HANDLERS[hand_name]

        tool_registry.register(
            name=tool_name,
            schema=schema,
            handler=handler,
            category="hands",
            tags=["hands", hand_name, "local"],
            source_module="infrastructure.hands.tools",
            requires_confirmation=(hand_name == "shell"),
        )
        count += 1

    logger.info("Registered %d local hand tools in MCP registry", count)
    return count


def get_local_hands_for_persona(persona_id: str) -> list[str]:
    """Return the local hand tool names available to a persona."""
    hand_names = PERSONA_LOCAL_HAND_MAP.get(persona_id, [])
    return [f"hand_{h}" for h in hand_names]
