"""Tests for tools.image_tools — Image generation (Pixel persona).

Heavy AI model tests are skipped; only catalogue, metadata, and
interface tests run in CI.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from creative.tools.image_tools import (
    IMAGE_TOOL_CATALOG,
    generate_image,
    generate_storyboard,
    image_variations,
    _save_metadata,
)


class TestImageToolCatalog:
    def test_catalog_has_all_tools(self):
        expected = {"generate_image", "generate_storyboard", "image_variations"}
        assert expected == set(IMAGE_TOOL_CATALOG.keys())

    def test_catalog_entries_have_required_keys(self):
        for tool_id, info in IMAGE_TOOL_CATALOG.items():
            assert "name" in info
            assert "description" in info
            assert "fn" in info
            assert callable(info["fn"])


class TestSaveMetadata:
    def test_saves_json_sidecar(self, tmp_path):
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"fake image")
        meta = {"prompt": "a cat", "width": 512}
        result = _save_metadata(img_path, meta)
        assert result.suffix == ".json"
        assert result.exists()

        import json
        data = json.loads(result.read_text())
        assert data["prompt"] == "a cat"


class TestGenerateImageInterface:
    def test_raises_without_creative_deps(self):
        """generate_image raises ImportError when diffusers not available."""
        with patch("creative.tools.image_tools._pipeline", None):
            with patch("creative.tools.image_tools._get_pipeline", side_effect=ImportError("no diffusers")):
                with pytest.raises(ImportError):
                    generate_image("a cat")

    def test_generate_image_with_mocked_pipeline(self, tmp_path):
        """generate_image works end-to-end with a mocked pipeline."""
        import sys

        mock_image = MagicMock()
        mock_image.save = MagicMock()

        mock_pipe = MagicMock()
        mock_pipe.device = "cpu"
        mock_pipe.return_value.images = [mock_image]

        mock_torch = MagicMock()
        mock_torch.Generator.return_value = MagicMock()

        with patch.dict(sys.modules, {"torch": mock_torch}):
            with patch("creative.tools.image_tools._get_pipeline", return_value=mock_pipe):
                with patch("creative.tools.image_tools._output_dir", return_value=tmp_path):
                    result = generate_image("a cat", width=512, height=512, steps=1)

        assert result["success"]
        assert result["prompt"] == "a cat"
        assert result["width"] == 512
        assert "path" in result


class TestGenerateStoryboardInterface:
    def test_calls_generate_image_per_scene(self):
        """Storyboard calls generate_image once per scene."""
        call_count = 0

        def mock_gen_image(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            return {
                "success": True, "path": f"/fake/{call_count}.png",
                "id": str(call_count), "prompt": prompt,
            }

        with patch("creative.tools.image_tools.generate_image", side_effect=mock_gen_image):
            result = generate_storyboard(
                ["sunrise", "mountain peak", "sunset"],
                steps=1,
            )

        assert result["success"]
        assert result["frame_count"] == 3
        assert len(result["frames"]) == 3
        assert call_count == 3


class TestImageVariationsInterface:
    def test_generates_multiple_variations(self):
        """image_variations generates the requested number of results."""
        def mock_gen_image(prompt, **kwargs):
            return {
                "success": True, "path": "/fake.png",
                "id": "x", "prompt": prompt,
                "seed": kwargs.get("seed"),
            }

        with patch("creative.tools.image_tools.generate_image", side_effect=mock_gen_image):
            result = image_variations("a dog", count=3, steps=1)

        assert result["success"]
        assert result["count"] == 3
        assert len(result["variations"]) == 3
