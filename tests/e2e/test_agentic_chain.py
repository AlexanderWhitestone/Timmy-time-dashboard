"""E2E: verify multi-step tool chaining works end-to-end.

These tests validate the full agentic loop pipeline: planning,
execution, adaptation, and progress tracking.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from timmy.agentic_loop import run_agentic_loop


def _mock_run(content: str):
    """Create a mock return value for agent.run()."""
    m = MagicMock()
    m.content = content
    return m


@pytest.mark.asyncio
async def test_multistep_chain_completes_all_steps():
    """GREEN PATH: multi-step prompt executes all steps."""
    mock_agent = MagicMock()
    mock_agent.run = MagicMock(side_effect=[
        _mock_run("1. Search AI news\n2. Write to file\n3. Verify"),
        _mock_run("Found 5 articles about AI in March 2026."),
        _mock_run("Wrote summary to /tmp/ai_news.md"),
        _mock_run("File exists, 15 lines."),
        _mock_run("Searched, wrote, verified."),
    ])

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        result = await run_agentic_loop("Search AI news and write summary to file")

    assert result.status == "completed"
    assert len(result.steps) == 3
    assert mock_agent.run.call_count == 5  # plan + 3 steps + summary


@pytest.mark.asyncio
async def test_multistep_chain_adapts_on_failure():
    """Step failure -> model adapts -> continues."""
    mock_agent = MagicMock()
    mock_agent.run = MagicMock(side_effect=[
        _mock_run("1. Read config\n2. Update setting\n3. Verify"),
        _mock_run("Config: timeout=30"),
        Exception("Permission denied"),
        _mock_run("Adapted: wrote to ~/config.yaml instead"),
        _mock_run("Verified: timeout=60"),
        _mock_run("Updated config. Used ~/config.yaml due to permissions."),
    ])

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        result = await run_agentic_loop("Update config timeout to 60")

    assert result.status == "completed"
    assert any(s.status == "adapted" for s in result.steps)


@pytest.mark.asyncio
async def test_max_steps_enforced():
    """Loop stops at max_steps."""
    mock_agent = MagicMock()
    mock_agent.run = MagicMock(side_effect=[
        _mock_run("1. A\n2. B\n3. C\n4. D\n5. E"),
        _mock_run("A done"),
        _mock_run("B done"),
        _mock_run("Completed 2 of 5 steps."),
    ])

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        result = await run_agentic_loop("Do 5 things", max_steps=2)

    assert len(result.steps) == 2
    assert result.status == "partial"


@pytest.mark.asyncio
async def test_progress_events_fire():
    """Progress callback fires per step."""
    events = []

    async def on_progress(desc, step, total):
        events.append((step, total))

    mock_agent = MagicMock()
    mock_agent.run = MagicMock(side_effect=[
        _mock_run("1. Do A\n2. Do B"),
        _mock_run("A done"),
        _mock_run("B done"),
        _mock_run("All done"),
    ])

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        await run_agentic_loop("Do A and B", on_progress=on_progress)

    assert len(events) == 2
    assert events[0] == (1, 2)
    assert events[1] == (2, 2)
