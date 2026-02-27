"""Tests for the custom models API routes."""

from unittest.mock import patch, MagicMock

import pytest

from infrastructure.models.registry import (
    CustomModel,
    ModelFormat,
    ModelRegistry,
    ModelRole,
)


@pytest.fixture
def registry(tmp_path):
    """A fresh ModelRegistry for each test."""
    db = tmp_path / "api_test.db"
    with patch("infrastructure.models.registry.DB_PATH", db):
        reg = ModelRegistry()
        yield reg


class TestModelsAPIList:
    """Test listing models via the API."""

    def test_list_models_empty(self, client, tmp_path):
        db = tmp_path / "api.db"
        with patch("infrastructure.models.registry.DB_PATH", db):
            with patch(
                "dashboard.routes.models.model_registry"
            ) as mock_reg:
                mock_reg.list_models.return_value = []
                resp = client.get("/api/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "total" in data

    def test_list_models_with_data(self, client):
        model = CustomModel(
            name="test-m",
            format=ModelFormat.OLLAMA,
            path="llama3.2",
            role=ModelRole.GENERAL,
        )
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.list_models.return_value = [model]
            resp = client.get("/api/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "test-m"


class TestModelsAPIRegister:
    """Test model registration via the API."""

    def test_register_ollama_model(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.register.return_value = CustomModel(
                name="my-model",
                format=ModelFormat.OLLAMA,
                path="llama3.2",
                role=ModelRole.GENERAL,
            )
            resp = client.post(
                "/api/v1/models",
                json={
                    "name": "my-model",
                    "format": "ollama",
                    "path": "llama3.2",
                    "role": "general",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"]["name"] == "my-model"

    def test_register_invalid_format(self, client):
        resp = client.post(
            "/api/v1/models",
            json={
                "name": "bad-model",
                "format": "invalid_format",
                "path": "whatever",
            },
        )
        assert resp.status_code == 400
        assert "Invalid format" in resp.json()["detail"]

    def test_register_invalid_role(self, client):
        resp = client.post(
            "/api/v1/models",
            json={
                "name": "bad-model",
                "format": "ollama",
                "path": "llama3.2",
                "role": "invalid_role",
            },
        )
        assert resp.status_code == 400
        assert "Invalid role" in resp.json()["detail"]


class TestModelsAPIDelete:
    """Test model deletion via the API."""

    def test_delete_model(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.unregister.return_value = True
            resp = client.delete("/api/v1/models/my-model")
        assert resp.status_code == 200

    def test_delete_nonexistent(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.unregister.return_value = False
            resp = client.delete("/api/v1/models/nonexistent")
        assert resp.status_code == 404


class TestModelsAPIGet:
    """Test getting a specific model."""

    def test_get_model(self, client):
        model = CustomModel(
            name="my-model",
            format=ModelFormat.OLLAMA,
            path="llama3.2",
            role=ModelRole.GENERAL,
        )
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.get.return_value = model
            resp = client.get("/api/v1/models/my-model")
        assert resp.status_code == 200
        assert resp.json()["name"] == "my-model"

    def test_get_nonexistent(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.get.return_value = None
            resp = client.get("/api/v1/models/nonexistent")
        assert resp.status_code == 404


class TestModelsAPIAssignments:
    """Test agent model assignment endpoints."""

    def test_assign_model(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.assign_model.return_value = True
            resp = client.post(
                "/api/v1/models/assignments",
                json={"agent_id": "agent-1", "model_name": "my-model"},
            )
        assert resp.status_code == 200

    def test_assign_nonexistent_model(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.assign_model.return_value = False
            resp = client.post(
                "/api/v1/models/assignments",
                json={"agent_id": "agent-1", "model_name": "nonexistent"},
            )
        assert resp.status_code == 404

    def test_unassign_model(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.unassign_model.return_value = True
            resp = client.delete("/api/v1/models/assignments/agent-1")
        assert resp.status_code == 200

    def test_unassign_nonexistent(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.unassign_model.return_value = False
            resp = client.delete("/api/v1/models/assignments/nonexistent")
        assert resp.status_code == 404

    def test_list_assignments(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.get_agent_assignments.return_value = {
                "agent-1": "model-a",
                "agent-2": "model-b",
            }
            resp = client.get("/api/v1/models/assignments/all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2


class TestModelsAPIRoles:
    """Test role-based lookup endpoints."""

    def test_get_reward_model(self, client):
        model = CustomModel(
            name="reward-m",
            format=ModelFormat.OLLAMA,
            path="deepseek-r1:1.5b",
            role=ModelRole.REWARD,
        )
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.get_reward_model.return_value = model
            resp = client.get("/api/v1/models/roles/reward")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reward_model"]["name"] == "reward-m"

    def test_get_reward_model_none(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.get_reward_model.return_value = None
            resp = client.get("/api/v1/models/roles/reward")
        assert resp.status_code == 200
        assert resp.json()["reward_model"] is None

    def test_get_teacher_model(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.get_teacher_model.return_value = None
            resp = client.get("/api/v1/models/roles/teacher")
        assert resp.status_code == 200
        assert resp.json()["teacher_model"] is None


class TestModelsAPISetActive:
    """Test enable/disable model endpoint."""

    def test_enable_model(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.set_active.return_value = True
            resp = client.patch(
                "/api/v1/models/my-model/active",
                json={"active": True},
            )
        assert resp.status_code == 200

    def test_disable_nonexistent(self, client):
        with patch(
            "dashboard.routes.models.model_registry"
        ) as mock_reg:
            mock_reg.set_active.return_value = False
            resp = client.patch(
                "/api/v1/models/nonexistent/active",
                json={"active": False},
            )
        assert resp.status_code == 404
