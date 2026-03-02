"""Tests for health and sovereignty endpoints."""

import pytest
from unittest.mock import patch


class TestSovereigntyEndpoint:
    """Tests for /health/sovereignty endpoint."""

    def test_sovereignty_returns_overall_score(self, client):
        response = client.get("/health/sovereignty")
        assert response.status_code == 200
        data = response.json()
        assert "overall_score" in data
        assert isinstance(data["overall_score"], (int, float))
        assert 0 <= data["overall_score"] <= 10

    def test_sovereignty_returns_dependencies(self, client):
        response = client.get("/health/sovereignty")
        assert response.status_code == 200
        data = response.json()
        assert "dependencies" in data
        assert isinstance(data["dependencies"], list)
        for dep in data["dependencies"]:
            assert "name" in dep
            assert "status" in dep
            assert "sovereignty_score" in dep
            assert "details" in dep

    def test_sovereignty_returns_recommendations(self, client):
        response = client.get("/health/sovereignty")
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)

    def test_sovereignty_includes_timestamps(self, client):
        response = client.get("/health/sovereignty")
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data


class TestHealthComponentsEndpoint:
    """Tests for /health/components endpoint."""

    def test_components_returns_config(self, client):
        response = client.get("/health/components")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert "debug" in data["config"]
        assert "model_backend" in data["config"]


class TestScaryPathScenarios:
    """Scary path tests for production scenarios."""

    def test_concurrent_sovereignty_requests(self, client):
        import concurrent.futures

        def fetch():
            return client.get("/health/sovereignty")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch) for _ in range(10)]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert all(r.status_code == 200 for r in responses)
        for r in responses:
            data = r.json()
            assert "overall_score" in data

    def test_sovereignty_with_missing_dependencies(self, client):
        with patch("dashboard.routes.health.check_ollama", return_value=False):
            response = client.get("/health/sovereignty")
            assert response.status_code == 200
            data = response.json()
            assert "overall_score" in data
            assert "dependencies" in data
