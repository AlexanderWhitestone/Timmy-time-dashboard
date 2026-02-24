"""Tests for tools.music_tools — Music generation (Lyra persona).

Heavy AI model tests are skipped; only catalogue, interface, and
metadata tests run in CI.
"""

import pytest
from unittest.mock import patch, MagicMock

from tools.music_tools import (
    MUSIC_TOOL_CATALOG,
    GENRES,
    list_genres,
    generate_song,
    generate_instrumental,
    generate_vocals,
)


class TestMusicToolCatalog:
    def test_catalog_has_all_tools(self):
        expected = {
            "generate_song", "generate_instrumental",
            "generate_vocals", "list_genres",
        }
        assert expected == set(MUSIC_TOOL_CATALOG.keys())

    def test_catalog_entries_have_required_keys(self):
        for tool_id, info in MUSIC_TOOL_CATALOG.items():
            assert "name" in info
            assert "description" in info
            assert "fn" in info
            assert callable(info["fn"])


class TestListGenres:
    def test_returns_genre_list(self):
        result = list_genres()
        assert result["success"]
        assert len(result["genres"]) > 10
        assert "pop" in result["genres"]
        assert "cinematic" in result["genres"]


class TestGenres:
    def test_common_genres_present(self):
        for genre in ["pop", "rock", "hip-hop", "jazz", "electronic", "classical"]:
            assert genre in GENRES


class TestGenerateSongInterface:
    def test_raises_without_ace_step(self):
        with patch("tools.music_tools._model", None):
            with patch("tools.music_tools._get_model", side_effect=ImportError("no ace-step")):
                with pytest.raises(ImportError):
                    generate_song("la la la")

    def test_duration_clamped(self):
        """Duration is clamped to 30–240 range."""
        mock_audio = MagicMock()
        mock_audio.save = MagicMock()

        mock_model = MagicMock()
        mock_model.generate.return_value = mock_audio

        with patch("tools.music_tools._get_model", return_value=mock_model):
            with patch("tools.music_tools._output_dir", return_value=MagicMock()):
                with patch("tools.music_tools._save_metadata"):
                    # Should clamp 5 to 30
                    generate_song("lyrics", duration=5)
                    call_kwargs = mock_model.generate.call_args[1]
                    assert call_kwargs["duration"] == 30

    def test_generate_song_with_mocked_model(self, tmp_path):
        mock_audio = MagicMock()
        mock_audio.save = MagicMock()

        mock_model = MagicMock()
        mock_model.generate.return_value = mock_audio

        with patch("tools.music_tools._get_model", return_value=mock_model):
            with patch("tools.music_tools._output_dir", return_value=tmp_path):
                result = generate_song(
                    "hello world", genre="rock", duration=60, title="Test Song"
                )

        assert result["success"]
        assert result["genre"] == "rock"
        assert result["title"] == "Test Song"
        assert result["duration"] == 60


class TestGenerateInstrumentalInterface:
    def test_with_mocked_model(self, tmp_path):
        mock_audio = MagicMock()
        mock_audio.save = MagicMock()

        mock_model = MagicMock()
        mock_model.generate.return_value = mock_audio

        with patch("tools.music_tools._get_model", return_value=mock_model):
            with patch("tools.music_tools._output_dir", return_value=tmp_path):
                result = generate_instrumental("epic orchestral", genre="cinematic")

        assert result["success"]
        assert result["genre"] == "cinematic"
        assert result["instrumental"] is True


class TestGenerateVocalsInterface:
    def test_with_mocked_model(self, tmp_path):
        mock_audio = MagicMock()
        mock_audio.save = MagicMock()

        mock_model = MagicMock()
        mock_model.generate.return_value = mock_audio

        with patch("tools.music_tools._get_model", return_value=mock_model):
            with patch("tools.music_tools._output_dir", return_value=tmp_path):
                result = generate_vocals("do re mi", style="jazz")

        assert result["success"]
        assert result["vocals_only"] is True
        assert result["style"] == "jazz"
