"""Register OpenFang Hands as MCP tools in Timmy's tool registry.

Each OpenFang Hand becomes a callable MCP tool that personas can use
during task execution.  The mapping ensures the right personas get
access to the right hands:

    Mace (Security)  → collector (OSINT), browser
    Seer (Analytics) → predictor, researcher
    Echo (Research)  → researcher, browser, collector
    Helm (DevOps)    → browser
    Lead hand        → available to all personas via direct request

Call ``register_openfang_tools()`` during app startup (after config
is loaded) to populate the tool registry.
"""

import logging
from typing import Any

from infrastructure.openfang.client import OPENFANG_HANDS, openfang_client
from mcp.schemas.base import create_tool_schema

logger = logging.getLogger(__name__)

# ── Tool schemas ─────────────────────────────────────────────────────────────

_HAND_SCHEMAS: dict[str, dict] = {
    "browser": create_tool_schema(
        name="openfang_browser",
        description=(
            "Web automation via OpenFang's Browser hand. "
            "Navigates URLs, extracts content, fills forms. "
            "Includes mandatory purchase confirmation gates."
        ),
        parameters={
            "url": {"type": "string", "description": "URL to navigate to"},
            "instruction": {
                "type": "string",
                "description": "What to do on the page",
            },
        },
        required=["url"],
    ),
    "collector": create_tool_schema(
        name="openfang_collector",
        description=(
            "OSINT intelligence and continuous monitoring via OpenFang's "
            "Collector hand. Gathers public information on targets."
        ),
        parameters={
            "target": {
                "type": "string",
                "description": "Target to investigate (domain, org, person)",
            },
            "depth": {
                "type": "string",
                "description": "Collection depth: shallow | standard | deep",
                "default": "shallow",
            },
        },
        required=["target"],
    ),
    "predictor": create_tool_schema(
        name="openfang_predictor",
        description=(
            "Superforecasting with calibrated reasoning via OpenFang's "
            "Predictor hand. Produces probability estimates with reasoning."
        ),
        parameters={
            "question": {
                "type": "string",
                "description": "Forecasting question to evaluate",
            },
            "horizon": {
                "type": "string",
                "description": "Time horizon: 1d | 1w | 1m | 3m | 1y",
                "default": "1w",
            },
        },
        required=["question"],
    ),
    "lead": create_tool_schema(
        name="openfang_lead",
        description=(
            "Prospect discovery and ICP-based qualification via OpenFang's "
            "Lead hand. Finds and scores potential leads."
        ),
        parameters={
            "icp": {
                "type": "string",
                "description": "Ideal Customer Profile description",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum leads to return",
                "default": 10,
            },
        },
        required=["icp"],
    ),
    "twitter": create_tool_schema(
        name="openfang_twitter",
        description=(
            "Social account management via OpenFang's Twitter hand. "
            "Includes approval gates for sensitive actions."
        ),
        parameters={
            "action": {
                "type": "string",
                "description": "Action: post | reply | search | analyze",
            },
            "content": {
                "type": "string",
                "description": "Content for the action",
            },
        },
        required=["action", "content"],
    ),
    "researcher": create_tool_schema(
        name="openfang_researcher",
        description=(
            "Deep autonomous research with source verification via "
            "OpenFang's Researcher hand. Produces cited reports."
        ),
        parameters={
            "topic": {
                "type": "string",
                "description": "Research topic or question",
            },
            "depth": {
                "type": "string",
                "description": "Research depth: quick | standard | deep",
                "default": "standard",
            },
        },
        required=["topic"],
    ),
    "clip": create_tool_schema(
        name="openfang_clip",
        description=(
            "Video processing and social media publishing via OpenFang's "
            "Clip hand. Edits, captions, and publishes video content."
        ),
        parameters={
            "source": {
                "type": "string",
                "description": "Source video path or URL",
            },
            "instruction": {
                "type": "string",
                "description": "What to do with the video",
            },
        },
        required=["source"],
    ),
}

# Map personas to the OpenFang hands they should have access to
PERSONA_HAND_MAP: dict[str, list[str]] = {
    "echo": ["researcher", "browser", "collector"],
    "seer": ["predictor", "researcher"],
    "mace": ["collector", "browser"],
    "helm": ["browser"],
    "forge": ["browser", "researcher"],
    "quill": ["researcher"],
    "pixel": ["clip", "browser"],
    "lyra": [],
    "reel": ["clip"],
}


def _make_hand_handler(hand_name: str):
    """Create an async handler that delegates to the OpenFang client."""

    async def handler(**kwargs: Any) -> str:
        result = await openfang_client.execute_hand(hand_name, kwargs)
        if result.success:
            return result.output
        return f"[OpenFang {hand_name} error] {result.error}"

    handler.__name__ = f"openfang_{hand_name}"
    handler.__doc__ = _HAND_SCHEMAS.get(hand_name, {}).get(
        "description", f"OpenFang {hand_name} hand"
    )
    return handler


def register_openfang_tools() -> int:
    """Register all OpenFang Hands as MCP tools.

    Returns the number of tools registered.
    """
    from mcp.registry import tool_registry

    count = 0
    for hand_name in OPENFANG_HANDS:
        schema = _HAND_SCHEMAS.get(hand_name)
        if not schema:
            logger.warning("No schema for OpenFang hand: %s", hand_name)
            continue

        tool_name = f"openfang_{hand_name}"
        handler = _make_hand_handler(hand_name)

        tool_registry.register(
            name=tool_name,
            schema=schema,
            handler=handler,
            category="openfang",
            tags=["openfang", hand_name, "vendor"],
            source_module="infrastructure.openfang.tools",
            requires_confirmation=(hand_name in ("twitter",)),
        )
        count += 1

    logger.info("Registered %d OpenFang tools in MCP registry", count)
    return count


def get_hands_for_persona(persona_id: str) -> list[str]:
    """Return the OpenFang tool names available to a persona."""
    hand_names = PERSONA_HAND_MAP.get(persona_id, [])
    return [f"openfang_{h}" for h in hand_names]
