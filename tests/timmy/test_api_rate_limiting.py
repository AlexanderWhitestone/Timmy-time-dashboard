"""Tests for API rate limiting in Timmy Serve."""

import pytest
import time
from fastapi.testclient import TestClient
from timmy_serve.app import create_timmy_serve_app

@pytest.fixture
def client():
    app = create_timmy_serve_app()
    return TestClient(app)

def test_health_check_no_rate_limit(client):
    """Health check should not be rate limited (or have a very high limit)."""
    for _ in range(10):
        response = client.get("/health")
        assert response.status_code == 200

def test_chat_rate_limiting(client, monkeypatch):
    """Chat endpoint should be rate limited."""
    # Mock create_timmy to avoid heavy LLM initialization
    monkeypatch.setattr("timmy_serve.app.create_timmy", lambda: type('obj', (object,), {'run': lambda self, m, stream: type('obj', (object,), {'content': 'reply'})()})())
    
    # Send requests up to the limit (assuming limit is small for tests or we just test it's there)
    # Since we haven't implemented it yet, this test should fail if we assert 429
    responses = []
    for _ in range(20):
        responses.append(client.post("/serve/chat", json={"message": "hi"}))
    
    # If rate limiting is implemented, some of these should be 429
    status_codes = [r.status_code for r in responses]
    assert 429 in status_codes
