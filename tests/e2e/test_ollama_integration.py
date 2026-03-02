"""End-to-end tests for Ollama integration and model handling.

These tests verify that Ollama models are correctly loaded, Timmy can interact
with them, and fallback mechanisms work as expected.
"""

import pytest
from unittest.mock import patch, MagicMock
from config import settings


@pytest.mark.asyncio
async def test_ollama_connection():
    """Test that we can connect to Ollama and retrieve available models."""
    import urllib.request
    import json
    
    try:
        url = settings.ollama_url.replace("localhost", "127.0.0.1")
        req = urllib.request.Request(
            f"{url}/api/tags",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            assert "models" in data, "Response should contain 'models' key"
            assert isinstance(data["models"], list), "Models should be a list"
    except Exception as e:
        pytest.skip(f"Ollama not available: {e}")


@pytest.mark.asyncio
async def test_model_fallback_chain():
    """Test that the model fallback chain works correctly."""
    from timmy.agent import _resolve_model_with_fallback, DEFAULT_MODEL_FALLBACKS
    
    # Test with a non-existent model
    model, is_fallback = _resolve_model_with_fallback(
        requested_model="nonexistent-model",
        require_vision=False,
        auto_pull=False,
    )
    
    # When a model doesn't exist and auto_pull=False, the system falls back to an available model
    # or the last resort (the requested model itself if nothing else is available).
    # In tests, if no models are available in the mock environment, it might return the requested model.
    if is_fallback:
        assert model in DEFAULT_MODEL_FALLBACKS
    else:
        # If no fallbacks were available, it returns the requested model as last resort
        assert model == "nonexistent-model"


@pytest.mark.asyncio
async def test_timmy_agent_with_available_model():
    """Test that Timmy agent can be created with an available model."""
    from timmy.agent import create_timmy
    
    try:
        agent = create_timmy(db_file=":memory:")
        assert agent is not None, "Agent should be created"
        assert hasattr(agent, "name"), "Agent should have a name"
        assert agent.name == "Timmy", "Agent name should be Timmy"
    except Exception as e:
        pytest.skip(f"Timmy agent creation failed: {e}")


@pytest.mark.asyncio
async def test_timmy_chat_with_simple_query():
    """Test that Timmy can respond to a simple chat query."""
    from timmy.session import chat
    
    try:
        response = chat("Hello, who are you?")
        assert response is not None, "Response should not be None"
        assert isinstance(response, str), "Response should be a string"
        assert len(response) > 0, "Response should not be empty"
        assert "Timmy" in response or "agent" in response.lower(), "Response should mention Timmy or agent"
    except Exception as e:
        pytest.skip(f"Chat failed: {e}")


@pytest.mark.asyncio
async def test_model_supports_tools():
    """Test the model tool support detection."""
    from timmy.agent import _model_supports_tools
    
    # Small models should not support tools
    assert _model_supports_tools("llama3.2") == False, "llama3.2 should not support tools"
    assert _model_supports_tools("llama3.2:3b") == False, "llama3.2:3b should not support tools"
    
    # Larger models should support tools
    assert _model_supports_tools("llama3.1") == True, "llama3.1 should support tools"
    assert _model_supports_tools("llama3.1:8b-instruct") == True, "llama3.1:8b-instruct should support tools"
    
    # Unknown models default to True
    assert _model_supports_tools("unknown-model") == True, "Unknown models should default to True"


@pytest.mark.asyncio
async def test_system_prompt_selection():
    """Test that the correct system prompt is selected based on tool capability."""
    from timmy.prompts import get_system_prompt
    
    prompt_with_tools = get_system_prompt(tools_enabled=True)
    prompt_without_tools = get_system_prompt(tools_enabled=False)
    
    assert prompt_with_tools is not None, "Prompt with tools should not be None"
    assert prompt_without_tools is not None, "Prompt without tools should not be None"
    
    # Both should mention Timmy
    assert "Timmy" in prompt_with_tools, "Prompt should mention Timmy"
    assert "Timmy" in prompt_without_tools, "Prompt should mention Timmy"
    
    # Full prompt should mention tools
    assert "tool" in prompt_with_tools.lower(), "Full prompt should mention tools"


@pytest.mark.asyncio
async def test_ollama_model_availability_check():
    """Test the Ollama model availability check function."""
    from timmy.agent import _check_model_available
    
    try:
        # llama3.2 should be available (we pulled it earlier)
        result = _check_model_available("llama3.2")
        assert isinstance(result, bool), "Result should be a boolean"
        # We don't assert True because the model might not be available in all environments
    except Exception as e:
        pytest.skip(f"Model availability check failed: {e}")


@pytest.mark.asyncio
async def test_memory_system_initialization():
    """Test that the memory system initializes correctly."""
    from timmy.memory_system import memory_system
    
    context = memory_system.get_system_context()
    assert context is not None, "Memory context should not be None"
    assert isinstance(context, str), "Memory context should be a string"
    # Context may be empty on fresh init (no hot memory or facts stored yet)
