"""Tests for system introspection tools."""

import pytest


def test_get_system_info_returns_dict():
    """System info should return a dictionary."""
    from timmy.tools_intro import get_system_info

    info = get_system_info()

    assert isinstance(info, dict)
    assert "python_version" in info
    assert "platform" in info
    assert "model" in info
    assert "repo_root" in info


def test_get_system_info_contains_model():
    """System info should include model name."""
    from timmy.tools_intro import get_system_info
    from config import settings

    info = get_system_info()

    assert "model" in info
    # Model should come from settings
    assert info["model"] == settings.ollama_model


def test_get_system_info_contains_repo_root():
    """System info should include repo_root."""
    from timmy.tools_intro import get_system_info
    from config import settings

    info = get_system_info()

    assert "repo_root" in info
    assert info["repo_root"] == settings.repo_root
    # In Docker the CWD is /app, so just verify it's a non-empty path
    assert len(info["repo_root"]) > 0


def test_check_ollama_health_returns_dict():
    """Ollama health check should return a dictionary."""
    from timmy.tools_intro import check_ollama_health

    result = check_ollama_health()

    assert isinstance(result, dict)
    assert "accessible" in result
    assert "model" in result


def test_get_memory_status_returns_dict():
    """Memory status should return a dictionary with tier info."""
    from timmy.tools_intro import get_memory_status

    status = get_memory_status()

    assert isinstance(status, dict)
    assert "tier1_hot_memory" in status
    assert "tier2_vault" in status
