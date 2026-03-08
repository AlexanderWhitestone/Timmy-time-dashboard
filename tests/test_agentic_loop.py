"""Unit tests for the agentic loop module.

Tests cover planning, execution, max_steps enforcement, failure
adaptation, progress callbacks, and response cleaning.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from timmy.agentic_loop import (
    run_agentic_loop,
    _parse_steps,
    AgenticResult,
    AgenticStep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_run(content: str):
    """Create a mock return value for agent.run()."""
    m = MagicMock()
    m.content = content
    return m


# ---------------------------------------------------------------------------
# _parse_steps
# ---------------------------------------------------------------------------

class TestParseSteps:
    def test_numbered_with_dot(self):
        text = "1. Search for data\n2. Write to file\n3. Verify"
        assert _parse_steps(text) == ["Search for data", "Write to file", "Verify"]

    def test_numbered_with_paren(self):
        text = "1) Read config\n2) Update value\n3) Restart"
        assert _parse_steps(text) == ["Read config", "Update value", "Restart"]

    def test_fallback_plain_lines(self):
        text = "Search the web\nWrite results\nDone"
        assert _parse_steps(text) == ["Search the web", "Write results", "Done"]

    def test_empty_returns_empty(self):
        assert _parse_steps("") == []


# ---------------------------------------------------------------------------
# run_agentic_loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_planning_phase_produces_steps():
    """Planning prompt returns numbered step list."""
    mock_agent = MagicMock()
    mock_agent.run = MagicMock(side_effect=[
        _mock_run("1. Search AI news\n2. Write to file\n3. Verify"),
        _mock_run("Found 5 articles about AI."),
        _mock_run("Wrote summary to /tmp/ai_news.md"),
        _mock_run("File verified, 15 lines."),
        _mock_run("Searched, wrote, verified."),
    ])

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        result = await run_agentic_loop("Search AI news and write summary")

    assert result.status == "completed"
    assert len(result.steps) == 3


@pytest.mark.asyncio
async def test_loop_executes_all_steps():
    """Loop calls agent.run() for plan + each step + summary."""
    mock_agent = MagicMock()
    mock_agent.run = MagicMock(side_effect=[
        _mock_run("1. Do A\n2. Do B"),
        _mock_run("A done"),
        _mock_run("B done"),
        _mock_run("All done"),
    ])

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        result = await run_agentic_loop("Do A and B")

    # plan + 2 steps + summary = 4 calls
    assert mock_agent.run.call_count == 4
    assert len(result.steps) == 2


@pytest.mark.asyncio
async def test_loop_respects_max_steps():
    """Loop stops at max_steps and returns status='partial'."""
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
async def test_failure_triggers_adaptation():
    """Failed step feeds error back to model, step marked as adapted."""
    mock_agent = MagicMock()
    mock_agent.run = MagicMock(side_effect=[
        _mock_run("1. Read config\n2. Update setting\n3. Verify"),
        _mock_run("Config: timeout=30"),
        Exception("Permission denied"),
        _mock_run("Adapted: wrote to ~/config.yaml instead"),
        _mock_run("Verified: timeout=60"),
        _mock_run("Updated config via alternative path."),
    ])

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        result = await run_agentic_loop("Update config timeout to 60")

    assert result.status == "completed"
    assert any(s.status == "adapted" for s in result.steps)


@pytest.mark.asyncio
async def test_progress_callback_fires():
    """on_progress called for each step completion."""
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


@pytest.mark.asyncio
async def test_result_contains_step_metadata():
    """AgenticResult.steps has status and duration per step."""
    mock_agent = MagicMock()
    mock_agent.run = MagicMock(side_effect=[
        _mock_run("1. Search\n2. Write"),
        _mock_run("Found results"),
        _mock_run("Written to file"),
        _mock_run("Done"),
    ])

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        result = await run_agentic_loop("Search and write")

    for step in result.steps:
        assert step.status in ("completed", "failed", "adapted")
        assert step.duration_ms >= 0
        assert step.description
        assert step.result


@pytest.mark.asyncio
async def test_config_default_used():
    """When max_steps=0, uses settings.max_agent_steps."""
    mock_agent = MagicMock()
    # Return more steps than default config allows (10)
    steps_text = "\n".join(f"{i}. Step {i}" for i in range(1, 15))
    side_effects = [_mock_run(steps_text)]
    # 10 step results + summary
    for i in range(1, 11):
        side_effects.append(_mock_run(f"Step {i} done"))
    side_effects.append(_mock_run("Summary"))

    mock_agent.run = MagicMock(side_effect=side_effects)

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        result = await run_agentic_loop("Do 14 things", max_steps=0)

    # Should be capped at 10 (config default)
    assert len(result.steps) == 10


@pytest.mark.asyncio
async def test_planning_failure_returns_failed():
    """If the planning phase fails, result.status is 'failed'."""
    mock_agent = MagicMock()
    mock_agent.run = MagicMock(side_effect=Exception("Model offline"))

    with patch("timmy.agentic_loop._get_loop_agent", return_value=mock_agent), \
         patch("timmy.agentic_loop._broadcast_progress", new_callable=AsyncMock):
        result = await run_agentic_loop("Do something")

    assert result.status == "failed"
    assert "Planning failed" in result.summary
