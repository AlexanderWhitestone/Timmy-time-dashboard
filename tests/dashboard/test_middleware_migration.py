import pytest
from fastapi.testclient import TestClient
from dashboard.app import app

@pytest.fixture
def client():
    return TestClient(app)

def test_security_headers_middleware_is_used(client):
    """Verify that SecurityHeadersMiddleware is used instead of the inline function."""
    response = client.get("/")
    # SecurityHeadersMiddleware sets X-Frame-Options to 'DENY' by default
    # The inline function in app.py sets it to 'SAMEORIGIN'
    assert response.headers["X-Frame-Options"] == "DENY"
    # SecurityHeadersMiddleware also sets Permissions-Policy
    assert "Permissions-Policy" in response.headers

def test_request_logging_middleware_is_used(client):
    """Verify that RequestLoggingMiddleware is used."""
    response = client.get("/")
    # RequestLoggingMiddleware adds X-Correlation-ID to the response
    assert "X-Correlation-ID" in response.headers

def test_csrf_middleware_is_used():
    """Verify that CSRFMiddleware works correctly on a standalone app.

    The main app disables CSRF in test mode (TIMMY_TEST_MODE=1) so we test
    the middleware directly on an isolated FastAPI instance.
    """
    from fastapi import FastAPI
    from dashboard.middleware.csrf import CSRFMiddleware

    test_app = FastAPI()
    test_app.add_middleware(CSRFMiddleware)

    @test_app.get("/test")
    def get_endpoint():
        return {"ok": True}

    @test_app.post("/test")
    def post_endpoint():
        return {"ok": True}

    test_client = TestClient(test_app)

    # GET request should set a csrf_token cookie
    response = test_client.get("/test")
    assert "csrf_token" in response.cookies

    # POST request without token should be blocked (403)
    response = test_client.post("/test")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_INVALID"
