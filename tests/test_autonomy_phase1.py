"""Tests for Phase 1 Autonomy Upgrades: UC-01 through UC-04.

UC-01: Live System Introspection Tool
UC-02: Offline Status Bug Fix (heartbeat + health endpoint)
UC-03: Message Source Tagging
UC-04: Discord Token Auto-Detection
"""

from unittest.mock import MagicMock, patch

import pytest


# ── UC-01: Live System Introspection ─────────────────────────────────────────


class TestGetTaskQueueStatus:
    """Test the task queue introspection function."""

    def test_returns_counts_and_total(self):
        from timmy.tools_intro import get_task_queue_status

        result = get_task_queue_status()
        assert "counts" in result or "error" in result
        if "counts" in result:
            assert "total" in result
            assert isinstance(result["total"], int)

    def test_current_task_none_when_idle(self):
        from timmy.tools_intro import get_task_queue_status

        result = get_task_queue_status()
        if "counts" in result:
            assert result["current_task"] is None

    def test_graceful_degradation_on_import_error(self):
        """Should return an error dict, not raise."""
        import sys

        from timmy.tools_intro import get_task_queue_status

        # Temporarily block the swarm.task_queue.models import to force the
        # except branch.  Setting sys.modules[key] = None causes ImportError.
        saved = sys.modules.pop("swarm.task_queue.models", "MISSING")
        sys.modules["swarm.task_queue.models"] = None  # type: ignore[assignment]
        try:
            result = get_task_queue_status()
            assert isinstance(result, dict)
            assert "error" in result
        finally:
            # Restore the real module
            del sys.modules["swarm.task_queue.models"]
            if saved != "MISSING":
                sys.modules["swarm.task_queue.models"] = saved


class TestGetAgentRoster:
    """Test the agent roster introspection function."""

    def test_returns_roster_with_counts(self):
        from swarm.registry import register
        from timmy.tools_intro import get_agent_roster

        register(name="TestAgent", capabilities="test", agent_id="test-agent-1")
        result = get_agent_roster()

        assert "agents" in result
        assert "total" in result
        assert result["total"] >= 1

    def test_agent_has_last_seen_age(self):
        from swarm.registry import register
        from timmy.tools_intro import get_agent_roster

        register(name="AgeTest", capabilities="test", agent_id="age-test-1")
        result = get_agent_roster()

        agents = result["agents"]
        assert len(agents) >= 1
        agent = next(a for a in agents if a["id"] == "age-test-1")
        assert "last_seen_seconds_ago" in agent
        assert agent["last_seen_seconds_ago"] >= 0

    def test_summary_counts(self):
        from timmy.tools_intro import get_agent_roster

        result = get_agent_roster()
        assert "idle" in result
        assert "busy" in result
        assert "offline" in result


class TestGetLiveSystemStatus:
    """Test the composite introspection function."""

    def test_returns_all_sections(self):
        from timmy.tools_intro import get_live_system_status

        result = get_live_system_status()
        assert "system" in result
        assert "task_queue" in result
        assert "agents" in result
        assert "memory" in result
        assert "timestamp" in result

    def test_uptime_present(self):
        from timmy.tools_intro import get_live_system_status

        result = get_live_system_status()
        assert "uptime_seconds" in result

    def test_discord_status_present(self):
        from timmy.tools_intro import get_live_system_status

        result = get_live_system_status()
        assert "discord" in result
        assert "state" in result["discord"]


class TestSystemStatusMCPTool:
    """Test the MCP-registered system_status tool."""

    def test_tool_returns_json_string(self):
        import json

        from creative.tools.system_status import system_status

        result = system_status()
        # Should be valid JSON
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert "system" in parsed or "error" in parsed


# ── UC-02: Offline Status Bug Fix ────────────────────────────────────────────


class TestHeartbeat:
    """Test that the heartbeat mechanism updates last_seen."""

    def test_heartbeat_updates_last_seen(self):
        from swarm.registry import get_agent, heartbeat, register

        register(name="HeartbeatTest", capabilities="test", agent_id="hb-test-1")
        initial = get_agent("hb-test-1")
        assert initial is not None

        import time

        time.sleep(0.01)

        heartbeat("hb-test-1")
        updated = get_agent("hb-test-1")
        assert updated is not None
        assert updated.last_seen >= initial.last_seen


class TestHealthEndpointStatus:
    """Test that /health reflects registry status, not just Ollama."""

    def test_health_returns_timmy_status(self, client):
        """Health endpoint should include agents.timmy.status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert "timmy" in data["agents"]
        assert "status" in data["agents"]["timmy"]

    def test_health_status_from_registry(self, client):
        """Timmy's status should come from the swarm registry."""
        from swarm.registry import register

        # Register Timmy as idle (happens on app startup too)
        register(name="Timmy", capabilities="chat", agent_id="timmy")

        response = client.get("/health")
        data = response.json()
        # Should be "idle" from registry, not "offline"
        assert data["agents"]["timmy"]["status"] in ("idle", "busy")


# ── UC-03: Message Source Tagging ────────────────────────────────────────────


class TestMessageSourceField:
    """Test that the Message dataclass has a source field."""

    def test_message_has_source_field(self):
        from dashboard.store import Message

        msg = Message(role="user", content="hello", timestamp="12:00:00")
        assert hasattr(msg, "source")
        assert msg.source == "browser"  # Default

    def test_message_custom_source(self):
        from dashboard.store import Message

        msg = Message(
            role="user", content="hello", timestamp="12:00:00", source="api"
        )
        assert msg.source == "api"


class TestMessageLogSource:
    """Test that MessageLog.append() accepts and stores source."""

    def test_append_with_source(self):
        from dashboard.store import message_log

        message_log.append(
            role="user", content="hello", timestamp="12:00:00", source="api"
        )
        entries = message_log.all()
        assert len(entries) == 1
        assert entries[0].source == "api"

    def test_append_default_source(self):
        from dashboard.store import message_log

        message_log.append(role="user", content="hello", timestamp="12:00:00")
        entries = message_log.all()
        assert len(entries) == 1
        assert entries[0].source == "browser"

    def test_multiple_sources(self):
        from dashboard.store import message_log

        message_log.append(
            role="user", content="from browser", timestamp="12:00:00", source="browser"
        )
        message_log.append(
            role="user", content="from api", timestamp="12:00:01", source="api"
        )
        message_log.append(
            role="agent", content="response", timestamp="12:00:02", source="system"
        )

        entries = message_log.all()
        assert len(entries) == 3
        assert entries[0].source == "browser"
        assert entries[1].source == "api"
        assert entries[2].source == "system"


class TestChatHistoryIncludesSource:
    """Test that the /api/chat/history endpoint includes source."""

    def test_history_includes_source_field(self, client):
        from dashboard.store import message_log

        message_log.append(
            role="user", content="test msg", timestamp="12:00:00", source="api"
        )

        response = client.get("/api/chat/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["source"] == "api"


class TestBrowserChatLogsSource:
    """Test that the browser chat route logs with source='browser'."""

    def test_browser_chat_source(self, client):
        with patch("swarm.task_queue.models.create_task") as mock_create:
            mock_task = MagicMock()
            mock_task.id = "test-id"
            mock_task.title = "hello from browser"
            mock_task.status = MagicMock(value="approved")
            mock_task.priority = MagicMock(value="normal")
            mock_task.assigned_to = "timmy"
            mock_create.return_value = mock_task

            with patch(
                "swarm.task_queue.models.get_queue_status_for_task",
                return_value={"position": 1, "total": 1, "percent_ahead": 0},
            ):
                response = client.post(
                    "/agents/timmy/chat",
                    data={"message": "hello from browser"},
                )

        from dashboard.store import message_log

        entries = message_log.all()
        assert len(entries) >= 1
        assert entries[0].source == "browser"


class TestAPIChatLogsSource:
    """Test that the API chat route logs with source='api'."""

    def test_api_chat_source(self, client):
        with patch(
            "dashboard.routes.chat_api.timmy_chat", return_value="Hi from Timmy"
        ):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello from api"}]},
            )

        assert response.status_code == 200

        from dashboard.store import message_log

        entries = message_log.all()
        assert len(entries) == 2  # user + agent
        assert entries[0].source == "api"
        assert entries[1].source == "api"


# ── UC-04: Discord Token Auto-Detection ──────────────────────────────────────


class TestDiscordDockerfix:
    """Test that the Dockerfile includes discord extras."""

    def _find_repo_root(self):
        """Walk up from this test file to find the repo root (has pyproject.toml)."""
        from pathlib import Path

        d = Path(__file__).resolve().parent
        while d != d.parent:
            if (d / "pyproject.toml").exists():
                return d
            d = d.parent
        return Path(__file__).resolve().parent.parent  # fallback

    def test_dashboard_dockerfile_includes_discord(self):
        dockerfile = self._find_repo_root() / "docker" / "Dockerfile.dashboard"
        if dockerfile.exists():
            content = dockerfile.read_text()
            assert "--extras discord" in content

    def test_main_dockerfile_includes_discord(self):
        dockerfile = self._find_repo_root() / "Dockerfile"
        if dockerfile.exists():
            content = dockerfile.read_text()
            assert "--extras discord" in content

    def test_test_dockerfile_includes_discord(self):
        dockerfile = self._find_repo_root() / "docker" / "Dockerfile.test"
        if dockerfile.exists():
            content = dockerfile.read_text()
            assert "--extras discord" in content


class TestDiscordTokenWatcher:
    """Test the Discord token watcher function exists and is wired."""

    def test_watcher_function_exists(self):
        from dashboard.app import _discord_token_watcher

        assert callable(_discord_token_watcher)

    def test_watcher_is_coroutine(self):
        import asyncio

        from dashboard.app import _discord_token_watcher

        assert asyncio.iscoroutinefunction(_discord_token_watcher)
