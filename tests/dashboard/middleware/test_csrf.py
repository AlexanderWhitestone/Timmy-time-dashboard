"""Tests for CSRF protection middleware."""

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


class TestCSRFMiddleware:
    """Test CSRF token validation and generation."""

    @pytest.fixture(autouse=True)
    def enable_csrf(self):
        """Re-enable CSRF for these tests."""
        import os
        old_val = os.environ.get("TIMMY_DISABLE_CSRF")
        os.environ["TIMMY_DISABLE_CSRF"] = "0"
        yield
        if old_val is not None:
            os.environ["TIMMY_DISABLE_CSRF"] = old_val
        else:
            del os.environ["TIMMY_DISABLE_CSRF"]

    def test_csrf_token_generation(self):
        """CSRF token should be generated and stored in session/state."""
        from dashboard.middleware.csrf import generate_csrf_token
        
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()
        
        # Tokens should be non-empty strings
        assert isinstance(token1, str)
        assert len(token1) > 0
        
        # Each token should be unique
        assert token1 != token2

    def test_csrf_token_validation(self):
        """Valid CSRF tokens should pass validation."""
        from dashboard.middleware.csrf import generate_csrf_token, validate_csrf_token
        
        token = generate_csrf_token()
        
        # Same token should validate
        assert validate_csrf_token(token, token) is True
        
        # Different tokens should not validate
        assert validate_csrf_token(token, "different-token") is False
        
        # Empty tokens should not validate
        assert validate_csrf_token(token, "") is False
        assert validate_csrf_token("", token) is False

    def test_csrf_middleware_allows_safe_methods(self):
        """GET, HEAD, OPTIONS requests should not require CSRF token."""
        from dashboard.middleware.csrf import CSRFMiddleware
        
        app = FastAPI()
        app.add_middleware(CSRFMiddleware, secret="test-secret")
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "success"}
        
        client = TestClient(app)
        
        # GET should work without CSRF token
        response = client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

    def test_csrf_middleware_blocks_unsafe_methods_without_token(self):
        """POST, PUT, DELETE should require CSRF token."""
        from dashboard.middleware.csrf import CSRFMiddleware
        
        app = FastAPI()
        app.add_middleware(CSRFMiddleware, secret="test-secret")
        
        @app.post("/test")
        def test_endpoint():
            return {"message": "success"}
        
        client = TestClient(app)
        
        # POST without CSRF token should fail
        response = client.post("/test")
        assert response.status_code == 403
        assert "csrf" in response.json().get("error", "").lower()

    def test_csrf_middleware_allows_with_valid_token(self):
        """POST with valid CSRF token should succeed."""
        from dashboard.middleware.csrf import CSRFMiddleware, generate_csrf_token
        
        app = FastAPI()
        app.add_middleware(CSRFMiddleware, secret="test-secret")
        
        @app.post("/test")
        def test_endpoint():
            return {"message": "success"}
        
        client = TestClient(app)
        
        # Get CSRF token from cookie or header
        token = generate_csrf_token()
        
        # POST with valid CSRF token
        response = client.post(
            "/test",
            headers={"X-CSRF-Token": token},
            cookies={"csrf_token": token}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

    def test_csrf_middleware_exempt_routes(self):
        """Routes with webhook patterns should bypass CSRF validation."""
        from dashboard.middleware.csrf import CSRFMiddleware
        
        app = FastAPI()
        app.add_middleware(CSRFMiddleware, secret="test-secret")
        
        @app.post("/webhook")
        def webhook_endpoint():
            return {"message": "webhook received"}
        
        client = TestClient(app)
        
        # POST to exempt route without CSRF token should work
        response = client.post("/webhook")
        assert response.status_code == 200
        assert response.json() == {"message": "webhook received"}

    def test_csrf_token_in_cookie(self):
        """CSRF token should be set in cookie for frontend to read."""
        from dashboard.middleware.csrf import CSRFMiddleware
        
        app = FastAPI()
        app.add_middleware(CSRFMiddleware, secret="test-secret")
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "success"}
        
        client = TestClient(app)
        
        # GET should set CSRF cookie
        response = client.get("/test")
        assert response.status_code == 200
        assert "csrf_token" in response.cookies or "set-cookie" in str(response.headers).lower()

    def test_csrf_middleware_allows_with_form_field(self):
        """POST with valid CSRF token in form field should succeed."""
        from dashboard.middleware.csrf import CSRFMiddleware, generate_csrf_token
        
        app = FastAPI()
        app.add_middleware(CSRFMiddleware)
        
        @app.post("/test-form")
        async def test_endpoint(request: Request):
            return {"message": "success"}
        
        client = TestClient(app)
        token = generate_csrf_token()
        
        # POST with valid CSRF token in form field
        response = client.post(
            "/test-form",
            data={"csrf_token": token, "other": "data"},
            cookies={"csrf_token": token}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

    def test_csrf_middleware_blocks_mismatched_token(self):
        """POST with mismatched token should fail."""
        from dashboard.middleware.csrf import CSRFMiddleware, generate_csrf_token
        
        app = FastAPI()
        app.add_middleware(CSRFMiddleware)
        
        @app.post("/test")
        async def test_endpoint():
            return {"message": "success"}
        
        client = TestClient(app)
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()
        
        # POST with token from one session and cookie from another
        response = client.post(
            "/test",
            headers={"X-CSRF-Token": token1},
            cookies={"csrf_token": token2}
        )
        assert response.status_code == 403
        assert "CSRF" in response.json().get("error", "")

    def test_csrf_middleware_blocks_missing_cookie(self):
        """POST with header token but missing cookie should fail."""
        from dashboard.middleware.csrf import CSRFMiddleware, generate_csrf_token
        
        app = FastAPI()
        app.add_middleware(CSRFMiddleware)
        
        @app.post("/test")
        async def test_endpoint():
            return {"message": "success"}
        
        client = TestClient(app)
        token = generate_csrf_token()
        
        # POST with header token but no cookie
        response = client.post(
            "/test",
            headers={"X-CSRF-Token": token}
        )
        assert response.status_code == 403
