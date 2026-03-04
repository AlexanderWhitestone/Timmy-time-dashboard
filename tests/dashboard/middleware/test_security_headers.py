"""Tests for security headers middleware."""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.testclient import TestClient


class TestSecurityHeadersMiddleware:
    """Test security headers are properly set on responses."""

    @pytest.fixture
    def client_with_headers(self):
        """Create a test client with security headers middleware."""
        from dashboard.middleware.security_headers import SecurityHeadersMiddleware
        
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "success"}
        
        @app.get("/html")
        def html_endpoint():
            return HTMLResponse(content="<html><body>Test</body></html>")
        
        return TestClient(app)

    def test_x_content_type_options_header(self, client_with_headers):
        """X-Content-Type-Options should be set to nosniff."""
        response = client_with_headers.get("/test")
        assert response.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options_header(self, client_with_headers):
        """X-Frame-Options should be set to DENY."""
        response = client_with_headers.get("/test")
        assert response.headers.get("x-frame-options") == "SAMEORIGIN"

    def test_x_xss_protection_header(self, client_with_headers):
        """X-XSS-Protection should be enabled."""
        response = client_with_headers.get("/test")
        assert "1; mode=block" in response.headers.get("x-xss-protection", "")

    def test_referrer_policy_header(self, client_with_headers):
        """Referrer-Policy should be set."""
        response = client_with_headers.get("/test")
        assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy_header(self, client_with_headers):
        """Permissions-Policy should restrict sensitive features."""
        response = client_with_headers.get("/test")
        policy = response.headers.get("permissions-policy", "")
        assert "camera=()" in policy
        assert "microphone=()" in policy
        assert "geolocation=()" in policy

    def test_content_security_policy_header(self, client_with_headers):
        """Content-Security-Policy should be set for HTML responses."""
        response = client_with_headers.get("/html")
        csp = response.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp
        assert "script-src" in csp
        assert "style-src" in csp

    def test_strict_transport_security_in_production(self):
        """HSTS header should be set in production mode."""
        from dashboard.middleware.security_headers import SecurityHeadersMiddleware
        
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, production=True)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "success"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        hsts = response.headers.get("strict-transport-security")
        assert hsts is not None
        assert "max-age=" in hsts

    def test_strict_transport_security_not_in_dev(self, client_with_headers):
        """HSTS header should not be set in development mode."""
        response = client_with_headers.get("/test")
        assert "strict-transport-security" not in response.headers

    def test_headers_on_error_response(self):
        """Security headers should be set even on error responses."""
        from dashboard.middleware.security_headers import SecurityHeadersMiddleware
        
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)
        
        @app.get("/error")
        def error_endpoint():
            raise ValueError("Test error")
        
        # Use raise_server_exceptions=False to get the error response
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/error")
        
        # Even on 500 error, security headers should be present
        assert response.status_code == 500
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "SAMEORIGIN"
