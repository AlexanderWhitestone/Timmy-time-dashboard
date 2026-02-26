"""Functional tests for timmy_serve.voice_tts — TTS engine lifecycle.

pyttsx3 is not available in CI, so all tests mock the engine.
"""

import threading
from unittest.mock import patch, MagicMock, PropertyMock

import pytest


class TestVoiceTTS:
    """Test TTS engine initialization, speak, and configuration."""

    def test_init_success(self):
        mock_pyttsx3 = MagicMock()
        mock_engine = MagicMock()
        mock_pyttsx3.init.return_value = mock_engine

        with patch.dict("sys.modules", {"pyttsx3": mock_pyttsx3}):
            from timmy_serve.voice_tts import VoiceTTS
            tts = VoiceTTS(rate=200, volume=0.8)
            assert tts.available is True
            mock_engine.setProperty.assert_any_call("rate", 200)
            mock_engine.setProperty.assert_any_call("volume", 0.8)

    def test_init_failure_graceful(self):
        """When pyttsx3 import fails, VoiceTTS degrades gracefully."""
        with patch.dict("sys.modules", {"pyttsx3": None}):
            from importlib import reload
            import timmy_serve.voice_tts as mod
            tts = mod.VoiceTTS.__new__(mod.VoiceTTS)
            tts._engine = None
            tts._rate = 175
            tts._volume = 0.9
            tts._available = False
            tts._lock = threading.Lock()
            assert tts.available is False

    def test_speak_skips_when_unavailable(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = None
        tts._available = False
        tts._lock = threading.Lock()
        # Should not raise
        tts.speak("hello")

    def test_speak_sync_skips_when_unavailable(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = None
        tts._available = False
        tts._lock = threading.Lock()
        tts.speak_sync("hello")

    def test_speak_calls_engine(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = MagicMock()
        tts._available = True
        tts._lock = threading.Lock()

        tts.speak("test speech")
        # Give the background thread time to execute
        import time
        time.sleep(0.1)
        tts._engine.say.assert_called_with("test speech")

    def test_speak_sync_calls_engine(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = MagicMock()
        tts._available = True
        tts._lock = threading.Lock()

        tts.speak_sync("sync test")
        tts._engine.say.assert_called_with("sync test")
        tts._engine.runAndWait.assert_called_once()

    def test_set_rate(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = MagicMock()
        tts._rate = 175

        tts.set_rate(220)
        assert tts._rate == 220
        tts._engine.setProperty.assert_called_with("rate", 220)

    def test_set_rate_no_engine(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = None
        tts._rate = 175
        tts.set_rate(220)
        assert tts._rate == 220

    def test_set_volume_clamped(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = MagicMock()
        tts._volume = 0.9

        tts.set_volume(1.5)
        assert tts._volume == 1.0

        tts.set_volume(-0.5)
        assert tts._volume == 0.0

        tts.set_volume(0.7)
        assert tts._volume == 0.7

    def test_get_voices_no_engine(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = None
        assert tts.get_voices() == []

    def test_get_voices_with_engine(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        mock_voice = MagicMock()
        mock_voice.id = "voice1"
        mock_voice.name = "Default"
        mock_voice.languages = ["en"]

        tts._engine = MagicMock()
        tts._engine.getProperty.return_value = [mock_voice]

        voices = tts.get_voices()
        assert len(voices) == 1
        assert voices[0]["id"] == "voice1"
        assert voices[0]["name"] == "Default"
        assert voices[0]["languages"] == ["en"]

    def test_get_voices_exception(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = MagicMock()
        tts._engine.getProperty.side_effect = RuntimeError("no voices")
        assert tts.get_voices() == []

    def test_set_voice(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = MagicMock()
        tts.set_voice("voice_id_1")
        tts._engine.setProperty.assert_called_with("voice", "voice_id_1")

    def test_set_voice_no_engine(self):
        from timmy_serve.voice_tts import VoiceTTS
        tts = VoiceTTS.__new__(VoiceTTS)
        tts._engine = None
        tts.set_voice("voice_id_1")  # should not raise
