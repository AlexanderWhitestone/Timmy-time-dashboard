"""Tests for dashboard/routes/voice_enhanced.py — enhanced voice processing."""

from unittest.mock import MagicMock, patch

import pytest


class TestVoiceEnhancedProcess:
    """Test the POST /voice/enhanced/process endpoint."""

    def test_status_intent(self, client):
        resp = client.post(
            "/voice/enhanced/process",
            data={"text": "what is your status", "speak_response": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "status"
        assert "operational" in data["response"].lower()
        assert data["error"] is None

    def test_help_intent(self, client):
        resp = client.post(
            "/voice/enhanced/process",
            data={"text": "help me please", "speak_response": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "help"
        assert "commands" in data["response"].lower()

    def test_swarm_intent(self, client):
        resp = client.post(
            "/voice/enhanced/process",
            data={"text": "list all swarm agents", "speak_response": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "swarm"
        assert "agents" in data["response"].lower()

    def test_voice_intent(self, client):
        resp = client.post(
            "/voice/enhanced/process",
            data={"text": "change voice settings", "speak_response": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "voice"
        assert "tts" in data["response"].lower()

    def test_chat_fallback_intent(self, client):
        """Chat intent should attempt to call the Timmy agent."""
        mock_agent = MagicMock()
        mock_run = MagicMock()
        mock_run.content = "Hello from Timmy!"
        mock_agent.run.return_value = mock_run

        with patch("dashboard.routes.voice_enhanced.create_timmy", return_value=mock_agent):
            resp = client.post(
                "/voice/enhanced/process",
                data={"text": "tell me about Bitcoin", "speak_response": "false"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "chat"
        assert data["response"] == "Hello from Timmy!"

    def test_chat_fallback_error_handling(self, client):
        """When the agent raises, the error should be captured gracefully."""
        with patch(
            "dashboard.routes.voice_enhanced.create_timmy",
            side_effect=RuntimeError("Ollama offline"),
        ):
            resp = client.post(
                "/voice/enhanced/process",
                data={"text": "tell me about sovereignty", "speak_response": "false"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is not None
        assert "Ollama offline" in data["error"]

    def test_speak_response_flag(self, client):
        """When speak_response=true, the spoken field should be true."""
        resp = client.post(
            "/voice/enhanced/process",
            data={"text": "what is your status", "speak_response": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["spoken"] is True

    def test_confidence_returned(self, client):
        resp = client.post(
            "/voice/enhanced/process",
            data={"text": "status check", "speak_response": "false"},
        )
        data = resp.json()
        assert "confidence" in data
        assert isinstance(data["confidence"], (int, float))
