"""Functional tests for swarm.docker_runner — Docker container lifecycle.

All subprocess calls are mocked so Docker is not required.
"""

from unittest.mock import MagicMock, patch, call

import pytest

from swarm.docker_runner import DockerAgentRunner, ManagedContainer


class TestDockerAgentRunner:
    """Test container spawn/stop/list lifecycle."""

    def test_init_defaults(self):
        runner = DockerAgentRunner()
        assert runner.image == "timmy-time:latest"
        assert runner.coordinator_url == "http://dashboard:8000"
        assert runner.extra_env == {}
        assert runner._containers == {}

    def test_init_custom(self):
        runner = DockerAgentRunner(
            image="custom:v2",
            coordinator_url="http://host:9000",
            extra_env={"FOO": "bar"},
        )
        assert runner.image == "custom:v2"
        assert runner.coordinator_url == "http://host:9000"
        assert runner.extra_env == {"FOO": "bar"}

    @patch("swarm.docker_runner.subprocess.run")
    def test_spawn_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="abc123container\n", stderr=""
        )
        runner = DockerAgentRunner()
        info = runner.spawn("Echo", agent_id="test-id-1234", capabilities="summarise")

        assert info["container_id"] == "abc123container"
        assert info["agent_id"] == "test-id-1234"
        assert info["name"] == "Echo"
        assert info["capabilities"] == "summarise"
        assert "abc123container" in runner._containers

        # Verify docker command structure
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "docker"
        assert cmd[1] == "run"
        assert "--detach" in cmd
        assert "--name" in cmd
        assert "timmy-time:latest" in cmd

    @patch("swarm.docker_runner.subprocess.run")
    def test_spawn_generates_uuid_when_no_agent_id(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="cid\n", stderr="")
        runner = DockerAgentRunner()
        info = runner.spawn("Echo")
        # agent_id should be a valid UUID-like string
        assert len(info["agent_id"]) == 36  # UUID format

    @patch("swarm.docker_runner.subprocess.run")
    def test_spawn_custom_image(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="cid\n", stderr="")
        runner = DockerAgentRunner()
        info = runner.spawn("Echo", image="custom:latest")
        assert info["image"] == "custom:latest"

    @patch("swarm.docker_runner.subprocess.run")
    def test_spawn_docker_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="no such image"
        )
        runner = DockerAgentRunner()
        with pytest.raises(RuntimeError, match="no such image"):
            runner.spawn("Echo")

    @patch("swarm.docker_runner.subprocess.run", side_effect=FileNotFoundError)
    def test_spawn_docker_not_installed(self, mock_run):
        runner = DockerAgentRunner()
        with pytest.raises(RuntimeError, match="Docker CLI not found"):
            runner.spawn("Echo")

    @patch("swarm.docker_runner.subprocess.run")
    def test_stop_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="cid\n", stderr="")
        runner = DockerAgentRunner()
        # Spawn first
        runner.spawn("Echo", agent_id="a1")
        cid = list(runner._containers.keys())[0]

        mock_run.reset_mock()
        mock_run.return_value = MagicMock(returncode=0)

        assert runner.stop(cid) is True
        assert cid not in runner._containers
        # Verify docker rm -f was called
        rm_cmd = mock_run.call_args[0][0]
        assert rm_cmd[0] == "docker"
        assert rm_cmd[1] == "rm"
        assert "-f" in rm_cmd

    @patch("swarm.docker_runner.subprocess.run", side_effect=Exception("fail"))
    def test_stop_failure(self, mock_run):
        runner = DockerAgentRunner()
        runner._containers["fake"] = ManagedContainer(
            container_id="fake", agent_id="a", name="X", image="img"
        )
        assert runner.stop("fake") is False

    @patch("swarm.docker_runner.subprocess.run")
    def test_stop_all(self, mock_run):
        # Return different container IDs so they don't overwrite each other
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="cid_a\n", stderr=""),
            MagicMock(returncode=0, stdout="cid_b\n", stderr=""),
        ]
        runner = DockerAgentRunner()
        runner.spawn("A", agent_id="a1")
        runner.spawn("B", agent_id="a2")
        assert len(runner._containers) == 2

        mock_run.side_effect = None
        mock_run.return_value = MagicMock(returncode=0)
        stopped = runner.stop_all()
        assert stopped == 2
        assert len(runner._containers) == 0

    @patch("swarm.docker_runner.subprocess.run")
    def test_list_containers(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="cid\n", stderr="")
        runner = DockerAgentRunner()
        runner.spawn("Echo", agent_id="e1")
        containers = runner.list_containers()
        assert len(containers) == 1
        assert containers[0].name == "Echo"

    @patch("swarm.docker_runner.subprocess.run")
    def test_is_running_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="true\n", stderr="")
        runner = DockerAgentRunner()
        assert runner.is_running("somecid") is True

    @patch("swarm.docker_runner.subprocess.run")
    def test_is_running_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="false\n", stderr="")
        runner = DockerAgentRunner()
        assert runner.is_running("somecid") is False

    @patch("swarm.docker_runner.subprocess.run", side_effect=Exception("timeout"))
    def test_is_running_exception(self, mock_run):
        runner = DockerAgentRunner()
        assert runner.is_running("somecid") is False

    @patch("swarm.docker_runner.subprocess.run")
    def test_build_env_flags(self, mock_run):
        runner = DockerAgentRunner(extra_env={"CUSTOM": "val"})
        flags = runner._build_env_flags("agent-1", "Echo", "summarise")
        # Should contain pairs of --env KEY=VALUE
        env_dict = {}
        for i, f in enumerate(flags):
            if f == "--env" and i + 1 < len(flags):
                k, v = flags[i + 1].split("=", 1)
                env_dict[k] = v
        assert env_dict["COORDINATOR_URL"] == "http://dashboard:8000"
        assert env_dict["AGENT_NAME"] == "Echo"
        assert env_dict["AGENT_ID"] == "agent-1"
        assert env_dict["AGENT_CAPABILITIES"] == "summarise"
        assert env_dict["CUSTOM"] == "val"
