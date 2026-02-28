"""Tests for bug reports dashboard route."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Point task_queue and event_log SQLite to a temp directory."""
    db = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.task_queue.models.DB_PATH", db)
    monkeypatch.setattr("swarm.event_log.DB_PATH", db)


@pytest.fixture
def client():
    from dashboard.app import app

    with TestClient(app) as c:
        yield c


def test_bugs_page_loads(client):
    resp = client.get("/bugs")
    assert resp.status_code == 200
    assert "BUG REPORTS" in resp.text


def test_api_list_bugs(client):
    resp = client.get("/api/bugs")
    assert resp.status_code == 200
    data = resp.json()
    assert "bugs" in data
    assert "count" in data


def test_api_bug_stats(client):
    resp = client.get("/api/bugs/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "stats" in data
    assert "total" in data


def test_bugs_page_with_status_filter(client):
    resp = client.get("/bugs?status=approved")
    assert resp.status_code == 200
