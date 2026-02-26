"""TDD tests for swarm/agent_runner.py — sub-agent entry point.

Written RED-first: define expected behaviour, then make it pass.
"""

import asyncio
import signal
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def tmp_swarm_db(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.tasks.DB_PATH", db_path)
    monkeypatch.setattr("swarm.registry.DB_PATH", db_path)
    yield db_path


def test_agent_runner_module_is_importable():
    """The agent_runner module should import without errors."""
    import swarm.agent_runner
    assert hasattr(swarm.agent_runner, "main")


def test_agent_runner_main_is_coroutine():
    """main() should be an async function."""
    from swarm.agent_runner import main
    assert asyncio.iscoroutinefunction(main)


@pytest.mark.asyncio
async def test_agent_runner_creates_node_and_joins():
    """main() should create a SwarmNode and call join()."""
    mock_node = MagicMock()
    mock_node.join = AsyncMock()
    mock_node.leave = AsyncMock()

    with patch("sys.argv", ["agent_runner", "--agent-id", "test-1", "--name", "TestBot"]):
        with patch("swarm.swarm_node.SwarmNode", return_value=mock_node) as MockNodeClass:
            # We need to stop the event loop from waiting forever
            # Patch signal to immediately set the stop event
            original_signal = signal.signal

            def fake_signal(sig, handler):
                if sig in (signal.SIGTERM, signal.SIGINT):
                    # Immediately call the handler to stop the loop
                    handler(sig, None)
                return original_signal(sig, handler)

            with patch("signal.signal", side_effect=fake_signal):
                from swarm.agent_runner import main
                await main()

            MockNodeClass.assert_called_once_with("test-1", "TestBot")
            mock_node.join.assert_awaited_once()
            mock_node.leave.assert_awaited_once()


def test_agent_runner_has_dunder_main_guard():
    """The module should have an if __name__ == '__main__' guard."""
    import inspect
    import swarm.agent_runner
    source = inspect.getsource(swarm.agent_runner)
    assert '__name__' in source
    assert '__main__' in source
