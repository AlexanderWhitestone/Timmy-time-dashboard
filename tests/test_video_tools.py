"""Tests for tools.video_tools — Video generation (Reel persona).

Heavy AI model tests are skipped; only catalogue, interface, and
resolution preset tests run in CI.
"""

import pytest
from unittest.mock import patch, MagicMock

from tools.video_tools import (
    VIDEO_TOOL_CATALOG,
    RESOLUTION_PRESETS,
    VIDEO_STYLES,
    list_video_styles,
    generate_video_clip,
    image_to_video,
)


class TestVideoToolCatalog:
    def test_catalog_has_all_tools(self):
        expected = {"generate_video_clip", "image_to_video", "list_video_styles"}
        assert expected == set(VIDEO_TOOL_CATALOG.keys())

    def test_catalog_entries_have_required_keys(self):
        for tool_id, info in VIDEO_TOOL_CATALOG.items():
            assert "name" in info
            assert "description" in info
            assert "fn" in info
            assert callable(info["fn"])


class TestResolutionPresets:
    def test_480p_preset(self):
        assert RESOLUTION_PRESETS["480p"] == (854, 480)

    def test_720p_preset(self):
        assert RESOLUTION_PRESETS["720p"] == (1280, 720)


class TestVideoStyles:
    def test_common_styles_present(self):
        for style in ["cinematic", "anime", "documentary"]:
            assert style in VIDEO_STYLES


class TestListVideoStyles:
    def test_returns_styles_and_resolutions(self):
        result = list_video_styles()
        assert result["success"]
        assert "cinematic" in result["styles"]
        assert "480p" in result["resolutions"]
        assert "720p" in result["resolutions"]


class TestGenerateVideoClipInterface:
    def test_raises_without_creative_deps(self):
        with patch("tools.video_tools._t2v_pipeline", None):
            with patch("tools.video_tools._get_t2v_pipeline", side_effect=ImportError("no diffusers")):
                with pytest.raises(ImportError):
                    generate_video_clip("a sunset")

    def test_duration_clamped(self):
        """Duration is clamped to 2–10 range."""
        import sys

        mock_pipe = MagicMock()
        mock_pipe.device = "cpu"
        mock_result = MagicMock()
        mock_result.frames = [[MagicMock() for _ in range(48)]]
        mock_pipe.return_value = mock_result

        mock_torch = MagicMock()
        mock_torch.Generator.return_value = MagicMock()

        out_dir = MagicMock()
        out_dir.__truediv__ = MagicMock(return_value=MagicMock(__str__=lambda s: "/fake/clip.mp4"))

        with patch.dict(sys.modules, {"torch": mock_torch}):
            with patch("tools.video_tools._get_t2v_pipeline", return_value=mock_pipe):
                with patch("tools.video_tools._export_frames_to_mp4"):
                    with patch("tools.video_tools._output_dir", return_value=out_dir):
                        with patch("tools.video_tools._save_metadata"):
                            result = generate_video_clip("test", duration=50)
                            assert result["duration"] == 10  # clamped


class TestImageToVideoInterface:
    def test_raises_without_creative_deps(self):
        with patch("tools.video_tools._t2v_pipeline", None):
            with patch("tools.video_tools._get_t2v_pipeline", side_effect=ImportError("no diffusers")):
                with pytest.raises(ImportError):
                    image_to_video("/fake/image.png", "animate")
