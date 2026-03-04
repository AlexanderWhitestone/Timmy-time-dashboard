import pytest
from fastapi.testclient import TestClient
from dashboard.app import app

@pytest.fixture
def client():
    return TestClient(app)

def test_security_headers_middleware_is_used(client):
    """Verify that SecurityHeadersMiddleware is used instead of the inline function."""
    response = client.get("/")
    # SecurityHeadersMiddleware sets X-Frame-Options to 'SAMEORIGIN' by default
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    # SecurityHeadersMiddleware also sets Permissions-Policy
    assert "Permissions-Policy" in response.headers

def test_request_logging_middleware_is_used(client):
    """Verify that RequestLoggingMiddleware is used."""
    response = client.get("/")
    # RequestLoggingMiddleware adds X-Correlation-ID to the response
    assert "X-Correlation-ID" in response.headers

def test_csrf_middleware_is_used(client):
    """Verify that CSRFMiddleware is used."""
    import os
    old_val = os.environ.get("TIMMY_DISABLE_CSRF")
    os.environ["TIMMY_DISABLE_CSRF"] = "0"
    try:
        # GET request should set a csrf_token cookie if not present
        response = client.get("/")
        assert "csrf_token" in response.cookies
        
        # POST request without token should be blocked (403)
        # Use a path that isn't likely to be exempt
        response = client.post("/agents/create")
        assert response.status_code == 403
        assert response.json()["code"] == "CSRF_INVALID"
    finally:
        if old_val is not None:
            os.environ["TIMMY_DISABLE_CSRF"] = old_val
        else:
            del os.environ["TIMMY_DISABLE_CSRF"]
