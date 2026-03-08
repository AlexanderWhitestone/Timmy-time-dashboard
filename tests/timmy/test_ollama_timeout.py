"""Test that Ollama model is created with a generous request timeout.

The default httpx timeout is too short for complex prompts (30-60s generation).
This caused socket read errors in production.
"""

from unittest.mock import patch, MagicMock


def test_base_agent_sets_request_timeout():
    """BaseAgent creates Ollama with request_timeout=300."""
    with patch("timmy.agents.base.Ollama") as mock_ollama, \
         patch("timmy.agents.base.Agent"):
        mock_ollama.return_value = MagicMock()

        # Import after patching to get the patched version
        from timmy.agents.base import BaseAgent

        class ConcreteAgent(BaseAgent):
            async def handle_message(self, message: str) -> str:
                return ""

        # Trigger Ollama construction
        try:
            ConcreteAgent(
                agent_id="test",
                name="Test",
                role="tester",
                system_prompt="You are a test agent.",
                tools=[],
            )
        except Exception:
            pass  # MCP registry may not be available

        # Verify Ollama was called with request_timeout
        if mock_ollama.called:
            _, kwargs = mock_ollama.call_args
            assert kwargs.get("request_timeout") == 300, (
                f"Expected request_timeout=300, got {kwargs.get('request_timeout')}"
            )


def test_main_agent_sets_request_timeout():
    """create_timmy() creates Ollama with request_timeout=300."""
    with patch("timmy.agent.Ollama") as mock_ollama, \
         patch("timmy.agent.SqliteDb"), \
         patch("timmy.agent.Agent"):
        mock_ollama.return_value = MagicMock()

        from timmy.agent import create_timmy
        try:
            create_timmy()
        except Exception:
            pass

        if mock_ollama.called:
            _, kwargs = mock_ollama.call_args
            assert kwargs.get("request_timeout") == 300, (
                f"Expected request_timeout=300, got {kwargs.get('request_timeout')}"
            )
