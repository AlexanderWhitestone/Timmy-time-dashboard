"""Tests for CSRF protection middleware traversal bypasses."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from dashboard.middleware.csrf import CSRFMiddleware

class TestCSRFTraversal:
    """Test path traversal CSRF bypass."""

    @pytest.fixture(autouse=True)
    def enable_csrf(self):
        """Re-enable CSRF for these tests."""
        from config import settings
        original = settings.timmy_disable_csrf
        settings.timmy_disable_csrf = False
        yield
        settings.timmy_disable_csrf = original

    def test_csrf_middleware_path_traversal_bypass(self):
        """Test if path traversal can bypass CSRF exempt patterns."""
        app = FastAPI()
        app.add_middleware(CSRFMiddleware)
        
        @app.post("/test")
        def test_endpoint():
            return {"message": "success"}
        
        client = TestClient(app)
        
        # We want to check if the middleware logic is flawed.
        # Since TestClient might normalize, we can test the _is_likely_exempt method directly.
        middleware = CSRFMiddleware(app)
        
        # This path starts with /webhook, but resolves to /test
        traversal_path = "/webhook/../test"
        
        # If this returns True, it's a vulnerability because /test is not supposed to be exempt.
        is_exempt = middleware._is_likely_exempt(traversal_path)
        
        assert is_exempt is False, f"Path {traversal_path} should not be exempt"
