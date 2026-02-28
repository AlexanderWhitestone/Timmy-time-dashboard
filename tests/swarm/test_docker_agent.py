"""Tests for timmy/docker_agent.py — Docker container agent runner.

Tests the standalone Docker agent entry point that runs Timmy as a
swarm participant in a container.
"""

import subprocess
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Skip all tests in this module if Docker is not available
pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "docker"], capture_output=True).returncode != 0,
    reason="Docker not installed"
)


class TestDockerAgentMain:
    """Tests for the docker_agent main function."""

    @pytest.mark.asyncio
    async def test_main_exits_without_coordinator_url(self):
        """Main should exit early if COORDINATOR_URL is not set."""
        import timmy.docker_agent as docker_agent
        
        with patch.object(docker_agent, "COORDINATOR", ""):
            # Should return early without error
            await docker_agent.main()
            # No exception raised = success

    @pytest.mark.asyncio
    async def test_main_registers_timmy(self):
        """Main should register Timmy in the registry."""
        import timmy.docker_agent as docker_agent
        
        with patch.object(docker_agent, "COORDINATOR", "http://localhost:8000"):
            with patch.object(docker_agent, "AGENT_ID", "timmy"):
                with patch.object(docker_agent.registry, "register") as mock_register:
                    # Use return_value instead of side_effect to avoid coroutine issues
                    with patch.object(docker_agent, "_heartbeat_loop", new_callable=AsyncMock) as mock_hb:
                        with patch.object(docker_agent, "_task_loop", new_callable=AsyncMock) as mock_task:
                            # Stop the loops immediately by having them return instead of block
                            mock_hb.return_value = None
                            mock_task.return_value = None
                            
                            await docker_agent.main()
                            
                            mock_register.assert_called_once_with(
                                name="Timmy",
                                capabilities="chat,reasoning,research,planning",
                                agent_id="timmy",
                            )


class TestDockerAgentTaskExecution:
    """Tests for task execution in docker_agent."""

    @pytest.mark.asyncio
    async def test_run_task_executes_and_reports(self):
        """Task should be executed and result reported to coordinator."""
        import timmy.docker_agent as docker_agent
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        
        with patch.object(docker_agent, "COORDINATOR", "http://localhost:8000"):
            with patch("timmy.agent.create_timmy") as mock_create_timmy:
                mock_agent = MagicMock()
                mock_run_result = MagicMock()
                mock_run_result.content = "Task completed successfully"
                mock_agent.run.return_value = mock_run_result
                mock_create_timmy.return_value = mock_agent
                
                await docker_agent._run_task(
                    task_id="test-task-123",
                    description="Test task description",
                    client=mock_client,
                )
                
                # Verify result was posted to coordinator
                mock_client.post.assert_called_once()
                call_args = mock_client.post.call_args
                assert "/swarm/tasks/test-task-123/complete" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_run_task_handles_errors(self):
        """Task errors should be reported as failed results."""
        import timmy.docker_agent as docker_agent
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        
        with patch.object(docker_agent, "COORDINATOR", "http://localhost:8000"):
            with patch("timmy.agent.create_timmy") as mock_create_timmy:
                mock_create_timmy.side_effect = Exception("Agent creation failed")
                
                await docker_agent._run_task(
                    task_id="test-task-456",
                    description="Test task that fails",
                    client=mock_client,
                )
                
                # Verify error result was posted
                mock_client.post.assert_called_once()
                call_args = mock_client.post.call_args
                assert "error" in call_args[1]["data"]["result"].lower() or "Agent creation failed" in call_args[1]["data"]["result"]


class TestDockerAgentHeartbeat:
    """Tests for heartbeat functionality."""

    @pytest.mark.asyncio
    async def test_heartbeat_loop_updates_registry(self):
        """Heartbeat loop should update last_seen in registry."""
        import timmy.docker_agent as docker_agent
        
        with patch.object(docker_agent.registry, "heartbeat") as mock_heartbeat:
            stop_event = docker_agent.asyncio.Event()
            
            # Schedule stop after first heartbeat
            async def stop_after_delay():
                await docker_agent.asyncio.sleep(0.01)
                stop_event.set()
            
            # Run both coroutines
            await docker_agent.asyncio.gather(
                docker_agent._heartbeat_loop(stop_event),
                stop_after_delay(),
            )
            
            # Should have called heartbeat at least once
            assert mock_heartbeat.called


class TestDockerAgentTaskPolling:
    """Tests for task polling functionality."""

    @pytest.mark.asyncio
    async def test_task_loop_polls_for_tasks(self):
        """Task loop should poll coordinator for assigned tasks."""
        import timmy.docker_agent as docker_agent
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tasks": [
                {
                    "id": "task-123",
                    "description": "Do something",
                    "assigned_agent": "timmy",
                }
            ]
        }
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        
        stop_event = docker_agent.asyncio.Event()
        
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            
            # Schedule stop after first poll
            async def stop_after_delay():
                await docker_agent.asyncio.sleep(0.01)
                stop_event.set()
            
            await docker_agent.asyncio.gather(
                docker_agent._task_loop(stop_event),
                stop_after_delay(),
            )
            
            # Should have polled for tasks
            assert mock_client.get.called


class TestDockerAgentEnvironment:
    """Tests for environment variable handling."""

    def test_default_coordinator_url_empty(self):
        """Default COORDINATOR should be empty string."""
        import timmy.docker_agent as docker_agent
        
        # When env var is not set, should default to empty
        with patch.dict("os.environ", {}, clear=True):
            # Re-import to pick up new default
            import importlib
            mod = importlib.reload(docker_agent)
            assert mod.COORDINATOR == ""

    def test_default_agent_id(self):
        """Default agent ID should be 'timmy'."""
        import timmy.docker_agent as docker_agent
        
        with patch.dict("os.environ", {}, clear=True):
            import importlib
            mod = importlib.reload(docker_agent)
            assert mod.AGENT_ID == "timmy"

    def test_custom_agent_id_from_env(self):
        """AGENT_ID should be configurable via env var."""
        import timmy.docker_agent as docker_agent
        
        with patch.dict("os.environ", {"TIMMY_AGENT_ID": "custom-timmy"}):
            import importlib
            mod = importlib.reload(docker_agent)
            assert mod.AGENT_ID == "custom-timmy"
