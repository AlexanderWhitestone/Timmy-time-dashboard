"""Tests for Celery integration — graceful degradation when Celery is unavailable."""

import pytest


class TestCeleryClient:
    """Test the Celery client API gracefully degrades in test mode."""

    def test_submit_chat_task_returns_none_when_unavailable(self):
        from infrastructure.celery.client import submit_chat_task

        result = submit_chat_task("test prompt")
        assert result is None

    def test_submit_tool_task_returns_none_when_unavailable(self):
        from infrastructure.celery.client import submit_tool_task

        result = submit_tool_task("web_search", {"query": "test"})
        assert result is None

    def test_get_task_status_returns_none_when_unavailable(self):
        from infrastructure.celery.client import get_task_status

        result = get_task_status("fake-task-id")
        assert result is None

    def test_get_active_tasks_returns_empty_when_unavailable(self):
        from infrastructure.celery.client import get_active_tasks

        result = get_active_tasks()
        assert result == []

    def test_revoke_task_returns_false_when_unavailable(self):
        from infrastructure.celery.client import revoke_task

        result = revoke_task("fake-task-id")
        assert result is False


class TestCeleryApp:
    """Test the Celery app is None in test mode."""

    def test_celery_app_is_none_in_test_mode(self):
        from infrastructure.celery.app import celery_app

        assert celery_app is None


class TestBackgroundTaskTool:
    """Test the submit_background_task agent tool."""

    def test_returns_failure_when_celery_unavailable(self):
        from timmy.tools_celery import submit_background_task

        result = submit_background_task("research something")
        assert result["success"] is False
        assert result["task_id"] is None
        assert "not available" in result["error"]


class TestCeleryRoutes:
    """Test the Celery dashboard routes."""

    def test_celery_page_renders(self, client):
        response = client.get("/celery")
        assert response.status_code == 200
        assert "Background Tasks" in response.text

    def test_celery_api_returns_empty_list(self, client):
        response = client.get("/celery/api")
        assert response.status_code == 200
        assert response.json() == []

    def test_celery_submit_requires_prompt(self, client):
        response = client.post(
            "/celery/api",
            json={"agent_id": "timmy"},
        )
        assert response.status_code == 400

    def test_celery_submit_returns_503_when_unavailable(self, client):
        response = client.post(
            "/celery/api",
            json={"prompt": "do something", "agent_id": "timmy"},
        )
        assert response.status_code == 503

    def test_celery_task_status_returns_503_when_unavailable(self, client):
        response = client.get("/celery/api/fake-id")
        assert response.status_code == 503

    def test_celery_revoke_returns_503_when_unavailable(self, client):
        response = client.post("/celery/api/fake-id/revoke")
        assert response.status_code == 503
