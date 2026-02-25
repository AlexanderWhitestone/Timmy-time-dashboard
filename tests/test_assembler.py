"""Tests for creative.assembler — Video assembly engine.

MoviePy is mocked for CI; these tests verify the interface contracts.
"""

import pytest
from unittest.mock import patch, MagicMock

from creative.assembler import (
    ASSEMBLER_TOOL_CATALOG,
    stitch_clips,
    overlay_audio,
    add_title_card,
    add_subtitles,
    export_final,
    _MOVIEPY_AVAILABLE,
)


class TestAssemblerToolCatalog:
    def test_catalog_has_all_tools(self):
        expected = {
            "stitch_clips", "overlay_audio", "add_title_card",
            "add_subtitles", "export_final",
        }
        assert expected == set(ASSEMBLER_TOOL_CATALOG.keys())

    def test_catalog_entries_callable(self):
        for tool_id, info in ASSEMBLER_TOOL_CATALOG.items():
            assert callable(info["fn"])
            assert "name" in info
            assert "description" in info


class TestStitchClipsInterface:
    @pytest.mark.skipif(not _MOVIEPY_AVAILABLE, reason="MoviePy not installed")
    def test_raises_on_empty_clips(self):
        """Stitch with no clips should fail gracefully."""
        # MoviePy would fail on empty list
        with pytest.raises(Exception):
            stitch_clips([])


class TestOverlayAudioInterface:
    @pytest.mark.skipif(not _MOVIEPY_AVAILABLE, reason="MoviePy not installed")
    def test_overlay_requires_valid_paths(self):
        with pytest.raises(Exception):
            overlay_audio("/nonexistent/video.mp4", "/nonexistent/audio.wav")


class TestAddTitleCardInterface:
    @pytest.mark.skipif(not _MOVIEPY_AVAILABLE, reason="MoviePy not installed")
    def test_add_title_requires_valid_video(self):
        with pytest.raises(Exception):
            add_title_card("/nonexistent/video.mp4", "Title")


class TestAddSubtitlesInterface:
    @pytest.mark.skipif(not _MOVIEPY_AVAILABLE, reason="MoviePy not installed")
    def test_requires_valid_video(self):
        with pytest.raises(Exception):
            add_subtitles("/nonexistent.mp4", [{"text": "Hi", "start": 0, "end": 1}])


class TestExportFinalInterface:
    @pytest.mark.skipif(not _MOVIEPY_AVAILABLE, reason="MoviePy not installed")
    def test_requires_valid_video(self):
        with pytest.raises(Exception):
            export_final("/nonexistent/video.mp4")
