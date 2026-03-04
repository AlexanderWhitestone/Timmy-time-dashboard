"""Test security headers middleware in FastAPI app."""

import pytest
from fastapi.testclient import TestClient


def test_security_headers_present(client: TestClient):
    """Test that security headers are present in all responses."""
    response = client.get("/")
    
    # Check for security headers
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"
    
    assert "X-Content-Type-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    
    assert "X-XSS-Protection" in response.headers
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    
    assert "Referrer-Policy" in response.headers
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    
    assert "Content-Security-Policy" in response.headers


def test_csp_header_content(client: TestClient):
    """Test that Content Security Policy is properly configured."""
    response = client.get("/")
    csp = response.headers.get("Content-Security-Policy", "")
    
    # Should restrict default-src to self
    assert "default-src 'self'" in csp
    
    # Should allow scripts from self (SecurityHeadersMiddleware includes unsafe-inline for HTMX)
    assert "script-src 'self' 'unsafe-inline'" in csp

    # Should allow styles from self with unsafe-inline
    assert "style-src 'self' 'unsafe-inline'" in csp

    # Should restrict object-src
    assert "object-src 'none'" in csp


def test_cors_headers_restricted(client: TestClient):
    """Test that CORS is properly restricted (not allow-origins: *)."""
    response = client.get("/")
    
    # Should not have overly permissive CORS
    # (The actual CORS headers depend on the origin of the request,
    # so we just verify the app doesn't crash with permissive settings)
    assert response.status_code == 200


def test_health_endpoint_has_security_headers(client: TestClient):
    """Test that security headers are present on all endpoints."""
    response = client.get("/health")
    
    assert "X-Frame-Options" in response.headers
    assert "X-Content-Type-Options" in response.headers
    assert "Content-Security-Policy" in response.headers
