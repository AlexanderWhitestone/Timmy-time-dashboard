"""Tests for the custom model registry."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from infrastructure.models.registry import (
    CustomModel,
    ModelFormat,
    ModelRegistry,
    ModelRole,
)


@pytest.fixture
def registry(tmp_path):
    """Create a fresh ModelRegistry backed by a temporary database."""
    db = tmp_path / "test.db"
    with patch("infrastructure.models.registry.DB_PATH", db):
        reg = ModelRegistry()
        yield reg


@pytest.fixture
def sample_model():
    """A sample CustomModel for testing."""
    return CustomModel(
        name="test-llama",
        format=ModelFormat.OLLAMA,
        path="llama3.2",
        role=ModelRole.GENERAL,
        context_window=8192,
        description="Test model",
    )


@pytest.fixture
def reward_model():
    """A sample reward model."""
    return CustomModel(
        name="test-reward",
        format=ModelFormat.OLLAMA,
        path="deepseek-r1:1.5b",
        role=ModelRole.REWARD,
        context_window=32000,
        description="Test reward model",
    )


class TestModelCRUD:
    """Test model registration, lookup, and removal."""

    def test_register_model(self, registry, sample_model):
        registered = registry.register(sample_model)
        assert registered.name == "test-llama"
        assert registered.format == ModelFormat.OLLAMA

    def test_get_model(self, registry, sample_model):
        registry.register(sample_model)
        found = registry.get("test-llama")
        assert found is not None
        assert found.name == "test-llama"
        assert found.path == "llama3.2"

    def test_get_nonexistent_model(self, registry):
        assert registry.get("nonexistent") is None

    def test_list_models(self, registry, sample_model, reward_model):
        registry.register(sample_model)
        registry.register(reward_model)
        all_models = registry.list_models()
        assert len(all_models) == 2

    def test_list_models_by_role(self, registry, sample_model, reward_model):
        registry.register(sample_model)
        registry.register(reward_model)
        general = registry.list_models(role=ModelRole.GENERAL)
        assert len(general) == 1
        assert general[0].name == "test-llama"
        rewards = registry.list_models(role=ModelRole.REWARD)
        assert len(rewards) == 1
        assert rewards[0].name == "test-reward"

    def test_unregister_model(self, registry, sample_model):
        registry.register(sample_model)
        assert registry.unregister("test-llama") is True
        assert registry.get("test-llama") is None

    def test_unregister_nonexistent(self, registry):
        assert registry.unregister("nonexistent") is False

    def test_set_active(self, registry, sample_model):
        registry.register(sample_model)
        assert registry.set_active("test-llama", False) is True
        model = registry.get("test-llama")
        assert model.active is False
        assert registry.set_active("test-llama", True) is True
        model = registry.get("test-llama")
        assert model.active is True

    def test_set_active_nonexistent(self, registry):
        assert registry.set_active("nonexistent", True) is False

    def test_register_replaces_existing(self, registry, sample_model):
        registry.register(sample_model)
        updated = CustomModel(
            name="test-llama",
            format=ModelFormat.GGUF,
            path="/new/path.gguf",
            role=ModelRole.GENERAL,
            description="Updated model",
        )
        registry.register(updated)
        found = registry.get("test-llama")
        assert found.format == ModelFormat.GGUF
        assert found.path == "/new/path.gguf"


class TestAgentAssignments:
    """Test agent-to-model assignment management."""

    def test_assign_model(self, registry, sample_model):
        registry.register(sample_model)
        assert registry.assign_model("agent-1", "test-llama") is True
        model = registry.get_agent_model("agent-1")
        assert model is not None
        assert model.name == "test-llama"

    def test_assign_nonexistent_model(self, registry):
        assert registry.assign_model("agent-1", "nonexistent") is False

    def test_unassign_model(self, registry, sample_model):
        registry.register(sample_model)
        registry.assign_model("agent-1", "test-llama")
        assert registry.unassign_model("agent-1") is True
        assert registry.get_agent_model("agent-1") is None

    def test_unassign_nonexistent(self, registry):
        assert registry.unassign_model("agent-1") is False

    def test_get_agent_model_none(self, registry):
        assert registry.get_agent_model("agent-1") is None

    def test_get_all_assignments(self, registry, sample_model, reward_model):
        registry.register(sample_model)
        registry.register(reward_model)
        registry.assign_model("agent-1", "test-llama")
        registry.assign_model("agent-2", "test-reward")
        assignments = registry.get_agent_assignments()
        assert len(assignments) == 2
        assert assignments["agent-1"] == "test-llama"
        assert assignments["agent-2"] == "test-reward"

    def test_unregister_removes_assignments(self, registry, sample_model):
        registry.register(sample_model)
        registry.assign_model("agent-1", "test-llama")
        registry.unregister("test-llama")
        assert registry.get_agent_model("agent-1") is None
        assert len(registry.get_agent_assignments()) == 0


class TestRoleLookups:
    """Test role-based model lookups."""

    def test_get_reward_model(self, registry, reward_model):
        registry.register(reward_model)
        found = registry.get_reward_model()
        assert found is not None
        assert found.name == "test-reward"
        assert found.role == ModelRole.REWARD

    def test_get_reward_model_none(self, registry):
        assert registry.get_reward_model() is None

    def test_get_teacher_model(self, registry):
        teacher = CustomModel(
            name="teacher-model",
            format=ModelFormat.OLLAMA,
            path="teacher:latest",
            role=ModelRole.TEACHER,
        )
        registry.register(teacher)
        found = registry.get_teacher_model()
        assert found is not None
        assert found.name == "teacher-model"

    def test_get_teacher_model_none(self, registry):
        assert registry.get_teacher_model() is None

    def test_inactive_reward_model_not_returned(self, registry, reward_model):
        registry.register(reward_model)
        registry.set_active("test-reward", False)
        assert registry.get_reward_model() is None


class TestCustomModelDataclass:
    """Test CustomModel construction."""

    def test_default_registered_at(self):
        model = CustomModel(
            name="test", format=ModelFormat.OLLAMA, path="test"
        )
        assert model.registered_at != ""

    def test_model_roles(self):
        assert ModelRole.GENERAL.value == "general"
        assert ModelRole.REWARD.value == "reward"
        assert ModelRole.TEACHER.value == "teacher"
        assert ModelRole.JUDGE.value == "judge"

    def test_model_formats(self):
        assert ModelFormat.GGUF.value == "gguf"
        assert ModelFormat.SAFETENSORS.value == "safetensors"
        assert ModelFormat.HF_CHECKPOINT.value == "hf"
        assert ModelFormat.OLLAMA.value == "ollama"
