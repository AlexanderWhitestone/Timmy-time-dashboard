"""Tests for creative.director — Creative Director pipeline.

Tests project management, pipeline orchestration, and tool catalogue.
All AI model calls are mocked.
"""

import pytest
from unittest.mock import patch, MagicMock

from creative.director import (
    create_project,
    get_project,
    list_projects,
    run_storyboard,
    run_music,
    run_video_generation,
    run_assembly,
    run_full_pipeline,
    CreativeProject,
    DIRECTOR_TOOL_CATALOG,
    _projects,
)


@pytest.fixture(autouse=True)
def clear_projects():
    """Clear project store between tests."""
    _projects.clear()
    yield
    _projects.clear()


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project with scenes."""
    with patch("creative.director._project_dir", return_value=tmp_path):
        result = create_project(
            title="Test Video",
            description="A test creative project",
            scenes=[
                {"description": "A sunrise over mountains"},
                {"description": "A river flowing through a valley"},
                {"description": "A sunset over the ocean"},
            ],
            lyrics="La la la, the sun rises high",
        )
    return result["project"]["id"]


class TestCreateProject:
    def test_creates_project(self, tmp_path):
        with patch("creative.director._project_dir", return_value=tmp_path):
            result = create_project("My Video", "A cool video")
        assert result["success"]
        assert result["project"]["title"] == "My Video"
        assert result["project"]["status"] == "planning"

    def test_project_has_id(self, tmp_path):
        with patch("creative.director._project_dir", return_value=tmp_path):
            result = create_project("Test", "Test")
        assert len(result["project"]["id"]) == 12

    def test_project_with_scenes(self, tmp_path):
        with patch("creative.director._project_dir", return_value=tmp_path):
            result = create_project(
                "Scenes", "With scenes",
                scenes=[{"description": "Scene 1"}, {"description": "Scene 2"}],
            )
        assert result["project"]["scene_count"] == 2


class TestGetProject:
    def test_get_existing(self, sample_project):
        result = get_project(sample_project)
        assert result is not None
        assert result["title"] == "Test Video"

    def test_get_nonexistent(self):
        assert get_project("bogus") is None


class TestListProjects:
    def test_empty(self):
        assert list_projects() == []

    def test_with_projects(self, sample_project, tmp_path):
        with patch("creative.director._project_dir", return_value=tmp_path):
            create_project("Second", "desc")
        assert len(list_projects()) == 2


class TestRunStoryboard:
    def test_fails_without_project(self):
        result = run_storyboard("bogus")
        assert not result["success"]
        assert "not found" in result["error"]

    def test_fails_without_scenes(self, tmp_path):
        with patch("creative.director._project_dir", return_value=tmp_path):
            result = create_project("Empty", "No scenes")
        pid = result["project"]["id"]
        result = run_storyboard(pid)
        assert not result["success"]
        assert "No scenes" in result["error"]

    def test_generates_frames(self, sample_project, tmp_path):
        mock_result = {
            "success": True,
            "frame_count": 3,
            "frames": [
                {"path": "/fake/1.png", "scene_index": 0, "prompt": "sunrise"},
                {"path": "/fake/2.png", "scene_index": 1, "prompt": "river"},
                {"path": "/fake/3.png", "scene_index": 2, "prompt": "sunset"},
            ],
        }
        with patch("tools.image_tools.generate_storyboard", return_value=mock_result):
            with patch("creative.director._save_project"):
                result = run_storyboard(sample_project)
        assert result["success"]
        assert result["frame_count"] == 3


class TestRunMusic:
    def test_fails_without_project(self):
        result = run_music("bogus")
        assert not result["success"]

    def test_generates_track(self, sample_project):
        mock_result = {
            "success": True, "path": "/fake/song.wav",
            "genre": "pop", "duration": 60,
        }
        with patch("tools.music_tools.generate_song", return_value=mock_result):
            with patch("creative.director._save_project"):
                result = run_music(sample_project, genre="pop")
        assert result["success"]
        assert result["path"] == "/fake/song.wav"


class TestRunVideoGeneration:
    def test_fails_without_project(self):
        result = run_video_generation("bogus")
        assert not result["success"]

    def test_generates_clips(self, sample_project):
        mock_clip = {
            "success": True, "path": "/fake/clip.mp4",
            "duration": 5,
        }
        with patch("tools.video_tools.generate_video_clip", return_value=mock_clip):
            with patch("tools.video_tools.image_to_video", return_value=mock_clip):
                with patch("creative.director._save_project"):
                    result = run_video_generation(sample_project)
        assert result["success"]
        assert result["clip_count"] == 3


class TestRunAssembly:
    def test_fails_without_project(self):
        result = run_assembly("bogus")
        assert not result["success"]

    def test_fails_without_clips(self, sample_project):
        result = run_assembly(sample_project)
        assert not result["success"]
        assert "No video clips" in result["error"]


class TestCreativeProject:
    def test_to_dict(self):
        p = CreativeProject(title="Test", description="Desc")
        d = p.to_dict()
        assert d["title"] == "Test"
        assert d["status"] == "planning"
        assert d["scene_count"] == 0
        assert d["has_storyboard"] is False
        assert d["has_music"] is False


class TestDirectorToolCatalog:
    def test_catalog_has_all_tools(self):
        expected = {
            "create_project", "run_storyboard", "run_music",
            "run_video_generation", "run_assembly", "run_full_pipeline",
        }
        assert expected == set(DIRECTOR_TOOL_CATALOG.keys())

    def test_catalog_entries_callable(self):
        for tool_id, info in DIRECTOR_TOOL_CATALOG.items():
            assert callable(info["fn"])
