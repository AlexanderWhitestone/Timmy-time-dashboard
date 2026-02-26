"""Tests for Self-Coding Dashboard Routes.

Tests API endpoints and HTMX views.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from dashboard.app import app
    return TestClient(app)


class TestSelfCodingPageRoutes:
    """Page route tests."""
    
    def test_main_page_loads(self, client):
        """Main self-coding page should load."""
        response = client.get("/self-coding")
        assert response.status_code == 200
        assert "Self-Coding" in response.text
    
    def test_journal_partial(self, client):
        """Journal partial should return HTML."""
        response = client.get("/self-coding/journal")
        assert response.status_code == 200
        # Should contain journal list or empty message
        assert "journal" in response.text.lower() or "no entries" in response.text.lower()
    
    def test_stats_partial(self, client):
        """Stats partial should return HTML."""
        response = client.get("/self-coding/stats")
        assert response.status_code == 200
        # Should contain stats cards
        assert "Total Attempts" in response.text or "success rate" in response.text.lower()
    
    def test_execute_form_partial(self, client):
        """Execute form partial should return HTML."""
        response = client.get("/self-coding/execute-form")
        assert response.status_code == 200
        assert "Task Description" in response.text
        assert "textarea" in response.text


class TestSelfCodingAPIRoutes:
    """API route tests."""
    
    def test_api_journal_list(self, client):
        """API should return journal entries."""
        response = client.get("/self-coding/api/journal")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
    
    def test_api_journal_list_with_limit(self, client):
        """API should respect limit parameter."""
        response = client.get("/self-coding/api/journal?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5
    
    def test_api_journal_detail_not_found(self, client):
        """API should return 404 for non-existent entry."""
        response = client.get("/self-coding/api/journal/99999")
        assert response.status_code == 404
    
    def test_api_stats(self, client):
        """API should return stats."""
        response = client.get("/self-coding/api/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_attempts" in data
        assert "success_rate" in data
        assert "recent_failures" in data
    
    def test_api_codebase_summary(self, client):
        """API should return codebase summary."""
        response = client.get("/self-coding/api/codebase/summary")
        assert response.status_code == 200
        
        data = response.json()
        assert "summary" in data
    
    def test_api_codebase_reindex(self, client):
        """API should trigger reindex."""
        response = client.post("/self-coding/api/codebase/reindex")
        assert response.status_code == 200
        
        data = response.json()
        assert "indexed" in data
        assert "failed" in data
        assert "skipped" in data


class TestSelfCodingExecuteEndpoint:
    """Execute endpoint tests."""
    
    def test_execute_api_endpoint(self, client):
        """Execute API endpoint should accept task."""
        # Note: This will actually try to execute, which may fail
        # In production, this should be mocked or require auth
        response = client.post(
            "/self-coding/api/execute",
            json={"task_description": "Test task that will fail preflight"}
        )
        
        # Should return response (success or failure)
        assert response.status_code == 200
        
        data = response.json()
        assert "success" in data
        assert "message" in data
    
    def test_execute_htmx_endpoint(self, client):
        """Execute HTMX endpoint should accept form data."""
        response = client.post(
            "/self-coding/execute",
            data={"task_description": "Test task that will fail preflight"}
        )
        
        # Should return HTML response
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestSelfCodingNavigation:
    """Navigation integration tests."""
    
    def test_nav_link_in_header(self, client):
        """Self-coding link should be in header."""
        response = client.get("/")
        assert response.status_code == 200
        assert "/self-coding" in response.text
        assert "SELF-CODING" in response.text
