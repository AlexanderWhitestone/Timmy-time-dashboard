"""Chunk 3: OpenFang MCP tool registration — test first, implement second.

Tests cover:
- register_openfang_tools() registers all 7 hands
- Each tool has correct category, tags, and schema
- Twitter hand requires confirmation
- Persona-hand mapping is correct
- Handler delegates to openfang_client.execute_hand()
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def clean_tool_registry():
    """Remove OpenFang tools between tests so registration is idempotent."""
    yield
    from mcp.registry import tool_registry

    for name in list(tool_registry._tools.keys()):
        if name.startswith("openfang_"):
            tool_registry.unregister(name)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_openfang_tools_count():
    """register_openfang_tools() should register exactly 7 tools."""
    from infrastructure.openfang.tools import register_openfang_tools

    count = register_openfang_tools()
    assert count == 7


def test_all_seven_hands_registered():
    """After registration, all 7 openfang_* tools exist in the registry."""
    from infrastructure.openfang.tools import register_openfang_tools
    from mcp.registry import tool_registry

    register_openfang_tools()

    expected = {
        "openfang_browser",
        "openfang_collector",
        "openfang_predictor",
        "openfang_lead",
        "openfang_twitter",
        "openfang_researcher",
        "openfang_clip",
    }
    registered = set(tool_registry.list_tools(category="openfang"))
    assert registered == expected


def test_tools_have_correct_category():
    """Every OpenFang tool should be in the 'openfang' category."""
    from infrastructure.openfang.tools import register_openfang_tools
    from mcp.registry import tool_registry

    register_openfang_tools()

    for name in tool_registry.list_tools(category="openfang"):
        record = tool_registry.get(name)
        assert record is not None
        assert record.category == "openfang"


def test_tools_have_vendor_tag():
    """Every OpenFang tool should be tagged with 'vendor'."""
    from infrastructure.openfang.tools import register_openfang_tools
    from mcp.registry import tool_registry

    register_openfang_tools()

    for name in tool_registry.list_tools(category="openfang"):
        record = tool_registry.get(name)
        assert "vendor" in record.tags
        assert "openfang" in record.tags


def test_twitter_requires_confirmation():
    """The twitter hand should require user confirmation before execution."""
    from infrastructure.openfang.tools import register_openfang_tools
    from mcp.registry import tool_registry

    register_openfang_tools()

    twitter = tool_registry.get("openfang_twitter")
    assert twitter is not None
    assert twitter.requires_confirmation is True


def test_non_twitter_no_confirmation():
    """Non-twitter hands should NOT require confirmation."""
    from infrastructure.openfang.tools import register_openfang_tools
    from mcp.registry import tool_registry

    register_openfang_tools()

    for name in ["openfang_browser", "openfang_collector", "openfang_predictor"]:
        record = tool_registry.get(name)
        assert record is not None
        assert record.requires_confirmation is False


def test_tools_have_schemas():
    """Every OpenFang tool should have a non-empty schema with 'name' and 'parameters'."""
    from infrastructure.openfang.tools import register_openfang_tools
    from mcp.registry import tool_registry

    register_openfang_tools()

    for name in tool_registry.list_tools(category="openfang"):
        record = tool_registry.get(name)
        assert record.schema
        assert "name" in record.schema
        assert "parameters" in record.schema


# ---------------------------------------------------------------------------
# Persona-hand mapping
# ---------------------------------------------------------------------------

def test_persona_hand_map_mace():
    """Mace (Security) should have collector and browser."""
    from infrastructure.openfang.tools import get_hands_for_persona

    hands = get_hands_for_persona("mace")
    assert "openfang_collector" in hands
    assert "openfang_browser" in hands


def test_persona_hand_map_seer():
    """Seer (Analytics) should have predictor and researcher."""
    from infrastructure.openfang.tools import get_hands_for_persona

    hands = get_hands_for_persona("seer")
    assert "openfang_predictor" in hands
    assert "openfang_researcher" in hands


def test_persona_hand_map_echo():
    """Echo (Research) should have researcher, browser, and collector."""
    from infrastructure.openfang.tools import get_hands_for_persona

    hands = get_hands_for_persona("echo")
    assert "openfang_researcher" in hands
    assert "openfang_browser" in hands
    assert "openfang_collector" in hands


def test_persona_hand_map_unknown():
    """Unknown persona should get empty list."""
    from infrastructure.openfang.tools import get_hands_for_persona

    hands = get_hands_for_persona("nonexistent")
    assert hands == []


# ---------------------------------------------------------------------------
# Handler delegation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handler_delegates_to_client():
    """Tool handler should call openfang_client.execute_hand()."""
    from infrastructure.openfang.client import HandResult
    from infrastructure.openfang.tools import register_openfang_tools
    from mcp.registry import tool_registry

    register_openfang_tools()

    mock_result = HandResult(
        hand="browser",
        success=True,
        output="Page loaded",
    )

    with patch(
        "infrastructure.openfang.tools.openfang_client"
    ) as mock_client:
        mock_client.execute_hand = AsyncMock(return_value=mock_result)

        record = tool_registry.get("openfang_browser")
        assert record is not None

        output = await record.handler(url="https://example.com")
        assert output == "Page loaded"
        mock_client.execute_hand.assert_called_once_with(
            "browser", {"url": "https://example.com"}
        )


@pytest.mark.asyncio
async def test_handler_returns_error_on_failure():
    """On failure, handler should return the error string (not raise)."""
    from infrastructure.openfang.client import HandResult
    from infrastructure.openfang.tools import register_openfang_tools
    from mcp.registry import tool_registry

    register_openfang_tools()

    mock_result = HandResult(
        hand="collector",
        success=False,
        error="Connection refused",
    )

    with patch(
        "infrastructure.openfang.tools.openfang_client"
    ) as mock_client:
        mock_client.execute_hand = AsyncMock(return_value=mock_result)

        record = tool_registry.get("openfang_collector")
        output = await record.handler(target="example.com")
        assert "error" in output.lower()
        assert "Connection refused" in output
