"""Tests for the Creative Studio dashboard route."""

import os
import pytest

os.environ.setdefault("TIMMY_TEST_MODE", "1")

from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with temp DB paths."""
    monkeypatch.setattr("swarm.tasks.DB_PATH", tmp_path / "swarm.db")
    monkeypatch.setattr("swarm.registry.DB_PATH", tmp_path / "swarm.db")
    monkeypatch.setattr("swarm.stats.DB_PATH", tmp_path / "swarm.db")
    monkeypatch.setattr("swarm.learner.DB_PATH", tmp_path / "swarm.db")

    from dashboard.app import app
    return TestClient(app)


class TestCreativeStudioPage:
    def test_creative_page_loads(self, client):
        resp = client.get("/creative/ui")
        assert resp.status_code == 200
        assert "Creative Studio" in resp.text

    def test_creative_page_has_tabs(self, client):
        resp = client.get("/creative/ui")
        assert "tab-images" in resp.text
        assert "tab-music" in resp.text
        assert "tab-video" in resp.text
        assert "tab-director" in resp.text

    def test_creative_page_shows_personas(self, client):
        resp = client.get("/creative/ui")
        assert "Pixel" in resp.text
        assert "Lyra" in resp.text
        assert "Reel" in resp.text


class TestCreativeAPI:
    def test_projects_api_empty(self, client):
        resp = client.get("/creative/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data

    def test_genres_api(self, client):
        resp = client.get("/creative/api/genres")
        assert resp.status_code == 200
        data = resp.json()
        assert "genres" in data

    def test_video_styles_api(self, client):
        resp = client.get("/creative/api/video-styles")
        assert resp.status_code == 200
        data = resp.json()
        assert "styles" in data
        assert "resolutions" in data
