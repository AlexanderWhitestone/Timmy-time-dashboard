"""Tests for timmy.session — persistent chat session with response sanitization."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_session_singleton():
    """Reset the module-level singleton between tests."""
    import timmy.session as mod
    mod._agent = None
    yield
    mod._agent = None


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------

def test_chat_returns_string():
    """chat() should return a plain string response."""
    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="Hello, sir.")

    with patch("timmy.session._get_agent", return_value=mock_agent):
        from timmy.session import chat
        result = chat("Hi Timmy")

    assert isinstance(result, str)
    assert "Hello, sir." in result


def test_chat_passes_session_id():
    """chat() should pass the session_id to agent.run()."""
    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="OK.")

    with patch("timmy.session._get_agent", return_value=mock_agent):
        from timmy.session import chat
        chat("test", session_id="my-session")

    _, kwargs = mock_agent.run.call_args
    assert kwargs["session_id"] == "my-session"


def test_chat_uses_default_session_id():
    """chat() should use 'dashboard' as the default session_id."""
    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="OK.")

    with patch("timmy.session._get_agent", return_value=mock_agent):
        from timmy.session import chat
        chat("test")

    _, kwargs = mock_agent.run.call_args
    assert kwargs["session_id"] == "dashboard"


def test_chat_singleton_agent_reused():
    """Calling chat() multiple times should reuse the same agent instance."""
    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="OK.")

    with patch("timmy.agent.create_timmy", return_value=mock_agent) as mock_factory:
        from timmy.session import chat
        chat("first message")
        chat("second message")

    # Factory called only once (singleton)
    mock_factory.assert_called_once()


def test_chat_extracts_user_name():
    """chat() should extract user name from message and persist to memory."""
    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="Nice to meet you!")

    mock_mem = MagicMock()

    with patch("timmy.session._get_agent", return_value=mock_agent), \
         patch("timmy.memory_system.memory_system", mock_mem):
        from timmy.session import chat
        chat("my name is Alex")

    mock_mem.update_user_fact.assert_called_once_with("Name", "Alex")


def test_chat_graceful_degradation_on_memory_failure():
    """chat() should still work if the conversation manager raises."""
    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="I'm operational.")

    with patch("timmy.session._get_agent", return_value=mock_agent), \
         patch("timmy.conversation.conversation_manager") as mock_cm:
        mock_cm.extract_user_name.side_effect = Exception("memory broken")

        from timmy.session import chat
        result = chat("test message")

    assert "operational" in result


# ---------------------------------------------------------------------------
# _clean_response()
# ---------------------------------------------------------------------------

def test_clean_response_strips_json_tool_calls():
    """JSON tool call blocks should be removed from response text."""
    from timmy.session import _clean_response

    dirty = 'Here is the answer. {"name": "python", "parameters": {"code": "0.15 * 3847.23", "variable_to_return": "result"}} The result is 577.'
    clean = _clean_response(dirty)

    assert '{"name"' not in clean
    assert '"parameters"' not in clean
    assert "The result is 577." in clean


def test_clean_response_strips_function_calls():
    """Function-call-style text should be removed."""
    from timmy.session import _clean_response

    dirty = 'I will search for that. memory_search(query="recall number") Found nothing.'
    clean = _clean_response(dirty)

    assert "memory_search(" not in clean
    assert "Found nothing." in clean


def test_clean_response_strips_chain_of_thought():
    """Chain-of-thought narration lines should be removed."""
    from timmy.session import _clean_response

    dirty = """Since there's no direct answer in my vault or hot memory, I'll use memory_search.
Using memory_search(query="what is special"), I found a context.
Here's a possible response:
77 is special because it's a prime number."""
    clean = _clean_response(dirty)

    assert "Since there's no" not in clean
    assert "Here's a possible" not in clean
    assert "77 is special" in clean


def test_clean_response_preserves_normal_text():
    """Normal text without tool artifacts should pass through unchanged."""
    from timmy.session import _clean_response

    normal = "The number 77 is the sum of the first seven primes: 2+3+5+7+11+13+17."
    assert _clean_response(normal) == normal


def test_clean_response_handles_empty_string():
    """Empty string should be returned as-is."""
    from timmy.session import _clean_response
    assert _clean_response("") == ""


def test_clean_response_handles_none():
    """None should be returned as-is."""
    from timmy.session import _clean_response
    assert _clean_response(None) is None


# ---------------------------------------------------------------------------
# reset_session()
# ---------------------------------------------------------------------------

def test_reset_session_clears_context():
    """reset_session() should clear the conversation context."""
    with patch("timmy.conversation.conversation_manager") as mock_cm:
        from timmy.session import reset_session
        reset_session("test-session")

    mock_cm.clear_context.assert_called_once_with("test-session")
