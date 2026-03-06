"""Tests for brain.worker — DistributedWorker capability detection + task execution."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from brain.worker import DistributedWorker


class TestWorkerInit:
    """Test worker initialization and capability detection."""

    @patch("brain.worker.DistributedWorker._detect_capabilities")
    def test_init_defaults(self, mock_caps):
        mock_caps.return_value = ["general"]
        worker = DistributedWorker()
        assert worker.running is False
        assert worker.node_id  # non-empty
        assert "general" in worker.capabilities

    @patch("brain.worker.DistributedWorker._detect_capabilities")
    def test_custom_brain_client(self, mock_caps):
        mock_caps.return_value = ["general"]
        mock_client = MagicMock()
        worker = DistributedWorker(brain_client=mock_client)
        assert worker.brain is mock_client

    @patch("brain.worker.DistributedWorker._detect_capabilities")
    def test_default_handlers_registered(self, mock_caps):
        mock_caps.return_value = ["general"]
        worker = DistributedWorker()
        assert "shell" in worker._handlers
        assert "creative" in worker._handlers
        assert "code" in worker._handlers
        assert "research" in worker._handlers
        assert "general" in worker._handlers


class TestCapabilityDetection:
    """Test individual capability detection methods."""

    @patch("brain.worker.DistributedWorker._detect_capabilities", return_value=["general"])
    def _make_worker(self, mock_caps):
        return DistributedWorker()

    @patch("brain.worker.subprocess.run")
    def test_has_gpu_nvidia(self, mock_run):
        worker = self._make_worker()
        mock_run.return_value = MagicMock(returncode=0)
        assert worker._has_gpu() is True

    @patch("brain.worker.subprocess.run", side_effect=OSError("no nvidia-smi"))
    @patch("brain.worker.os.path.exists", return_value=False)
    @patch("brain.worker.os.uname")
    def test_has_gpu_no_gpu(self, mock_uname, mock_exists, mock_run):
        worker = self._make_worker()
        mock_uname.return_value = MagicMock(sysname="Linux")
        assert worker._has_gpu() is False

    @patch("brain.worker.subprocess.run")
    def test_has_internet_true(self, mock_run):
        worker = self._make_worker()
        mock_run.return_value = MagicMock(returncode=0)
        assert worker._has_internet() is True

    @patch("brain.worker.subprocess.run", side_effect=OSError("no curl"))
    def test_has_internet_no_curl(self, mock_run):
        worker = self._make_worker()
        assert worker._has_internet() is False

    @patch("brain.worker.subprocess.run")
    def test_has_command_true(self, mock_run):
        worker = self._make_worker()
        mock_run.return_value = MagicMock(returncode=0)
        assert worker._has_command("docker") is True

    @patch("brain.worker.subprocess.run")
    def test_has_command_false(self, mock_run):
        worker = self._make_worker()
        mock_run.return_value = MagicMock(returncode=1)
        assert worker._has_command("nonexistent") is False

    @patch("brain.worker.subprocess.run", side_effect=OSError)
    def test_has_command_oserror(self, mock_run):
        worker = self._make_worker()
        assert worker._has_command("anything") is False


class TestRegisterHandler:
    """Test custom handler registration."""

    @patch("brain.worker.DistributedWorker._detect_capabilities", return_value=["general"])
    def test_register_adds_handler_and_capability(self, mock_caps):
        worker = DistributedWorker()

        async def custom_handler(content):
            return "custom result"

        worker.register_handler("custom_type", custom_handler)
        assert "custom_type" in worker._handlers
        assert "custom_type" in worker.capabilities


class TestTaskHandlers:
    """Test individual task handlers."""

    @patch("brain.worker.DistributedWorker._detect_capabilities", return_value=["general"])
    def _make_worker(self, mock_caps):
        worker = DistributedWorker()
        worker.brain = MagicMock()
        worker.brain.remember = AsyncMock()
        worker.brain.complete_task = AsyncMock()
        return worker

    async def test_handle_code(self):
        worker = self._make_worker()
        result = await worker._handle_code("write a function")
        assert "write a function" in result

    async def test_handle_research_no_internet(self):
        worker = self._make_worker()
        worker.capabilities = ["general"]  # no "web"
        with pytest.raises(Exception, match="Internet not available"):
            await worker._handle_research("search query")

    async def test_handle_creative_no_gpu(self):
        worker = self._make_worker()
        worker.capabilities = ["general"]  # no "gpu"
        with pytest.raises(Exception, match="GPU not available"):
            await worker._handle_creative("make an image")

    async def test_handle_general_no_ollama(self):
        worker = self._make_worker()
        worker.capabilities = ["general"]  # but not "ollama"
        # Remove "ollama" if present
        if "ollama" in worker.capabilities:
            worker.capabilities.remove("ollama")
        with pytest.raises(Exception, match="Ollama not available"):
            await worker._handle_general("answer this")


class TestExecuteTask:
    """Test execute_task orchestration."""

    @patch("brain.worker.DistributedWorker._detect_capabilities", return_value=["general"])
    def _make_worker(self, mock_caps):
        worker = DistributedWorker()
        worker.brain = MagicMock()
        worker.brain.complete_task = AsyncMock()
        return worker

    async def test_execute_task_success(self):
        worker = self._make_worker()

        async def fake_handler(content):
            return "result"

        worker._handlers["test_type"] = fake_handler

        result = await worker.execute_task({
            "id": 1,
            "type": "test_type",
            "content": "do it",
        })
        assert result["success"] is True
        assert result["result"] == "result"
        worker.brain.complete_task.assert_awaited_once_with(1, success=True, result="result")

    async def test_execute_task_failure(self):
        worker = self._make_worker()

        async def failing_handler(content):
            raise RuntimeError("oops")

        worker._handlers["fail_type"] = failing_handler

        result = await worker.execute_task({
            "id": 2,
            "type": "fail_type",
            "content": "fail",
        })
        assert result["success"] is False
        assert "oops" in result["error"]
        worker.brain.complete_task.assert_awaited_once()

    async def test_execute_task_falls_back_to_general(self):
        worker = self._make_worker()

        async def general_handler(content):
            return "general result"

        worker._handlers["general"] = general_handler

        result = await worker.execute_task({
            "id": 3,
            "type": "unknown_type",
            "content": "something",
        })
        assert result["success"] is True
        assert result["result"] == "general result"


class TestRunOnce:
    """Test run_once loop iteration."""

    @patch("brain.worker.DistributedWorker._detect_capabilities", return_value=["general"])
    def _make_worker(self, mock_caps):
        worker = DistributedWorker()
        worker.brain = MagicMock()
        worker.brain.claim_task = AsyncMock()
        worker.brain.complete_task = AsyncMock()
        return worker

    async def test_run_once_no_tasks(self):
        worker = self._make_worker()
        worker.brain.claim_task.return_value = None

        had_work = await worker.run_once()
        assert had_work is False

    async def test_run_once_with_task(self):
        worker = self._make_worker()
        worker.brain.claim_task.return_value = {
            "id": 1, "type": "code", "content": "write code"
        }

        had_work = await worker.run_once()
        assert had_work is True


class TestStopWorker:
    """Test stop method."""

    @patch("brain.worker.DistributedWorker._detect_capabilities", return_value=["general"])
    def test_stop_sets_running_false(self, mock_caps):
        worker = DistributedWorker()
        worker.running = True
        worker.stop()
        assert worker.running is False
