"""Chunk 4: ToolExecutor OpenFang delegation — test first, implement second.

Tests cover:
- When openfang_enabled=True and client healthy → delegates to OpenFang
- When openfang_enabled=False → falls back to existing behavior
- When OpenFang is down → falls back gracefully
- Hand matching from task descriptions
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Hand matching (pure function, no mocking needed)
# ---------------------------------------------------------------------------

def test_match_hand_from_description():
    """_match_openfang_hand should detect relevant hand from task text."""
    from swarm.tool_executor import _match_openfang_hand

    assert _match_openfang_hand("browse https://example.com") == "browser"
    assert _match_openfang_hand("navigate to the website") == "browser"
    assert _match_openfang_hand("collect OSINT on target.com") == "collector"
    assert _match_openfang_hand("predict whether Bitcoin hits 100k") == "predictor"
    assert _match_openfang_hand("forecast the election outcome") == "predictor"
    assert _match_openfang_hand("find leads matching our ICP") == "lead"
    assert _match_openfang_hand("prospect discovery for SaaS") == "lead"
    assert _match_openfang_hand("research quantum computing") == "researcher"
    assert _match_openfang_hand("investigate the supply chain") == "researcher"
    assert _match_openfang_hand("post a tweet about our launch") == "twitter"
    assert _match_openfang_hand("process this video clip") == "clip"


def test_match_hand_returns_none_for_unmatched():
    """Tasks with no OpenFang-relevant keywords return None."""
    from swarm.tool_executor import _match_openfang_hand

    assert _match_openfang_hand("write a Python function") is None
    assert _match_openfang_hand("fix the database migration") is None


# ---------------------------------------------------------------------------
# Delegation when enabled + healthy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openfang_delegation_when_enabled():
    """When openfang is enabled and healthy, try_openfang_execution delegates."""
    from infrastructure.openfang.client import HandResult

    mock_result = HandResult(
        hand="browser",
        success=True,
        output="OpenFang executed the task",
    )
    mock_client = MagicMock()
    mock_client.healthy = True
    mock_client.execute_hand = AsyncMock(return_value=mock_result)

    with patch("swarm.tool_executor.settings") as mock_settings, \
         patch("infrastructure.openfang.client.openfang_client", mock_client), \
         patch.dict("sys.modules", {}):  # force re-import
        mock_settings.openfang_enabled = True

        # Re-import to pick up patches
        from swarm.tool_executor import try_openfang_execution

        # Patch the lazy import inside try_openfang_execution
        with patch(
            "infrastructure.openfang.client.openfang_client", mock_client
        ):
            result = await try_openfang_execution(
                "browse https://example.com and extract headlines"
            )

    assert result is not None
    assert result["success"] is True
    assert "OpenFang" in result["result"]


# ---------------------------------------------------------------------------
# Fallback when disabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openfang_returns_none_when_disabled():
    """When openfang is disabled, try_openfang_execution returns None."""
    with patch("swarm.tool_executor.settings") as mock_settings:
        mock_settings.openfang_enabled = False

        from swarm.tool_executor import try_openfang_execution

        result = await try_openfang_execution("browse something")

    assert result is None


# ---------------------------------------------------------------------------
# Fallback when down
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openfang_returns_none_when_down():
    """When openfang is enabled but unhealthy, returns None (fallback)."""
    mock_client = MagicMock()
    mock_client.healthy = False

    with patch("swarm.tool_executor.settings") as mock_settings, \
         patch(
             "infrastructure.openfang.client.openfang_client", mock_client
         ):
        mock_settings.openfang_enabled = True

        from swarm.tool_executor import try_openfang_execution

        result = await try_openfang_execution("browse something")

    assert result is None
