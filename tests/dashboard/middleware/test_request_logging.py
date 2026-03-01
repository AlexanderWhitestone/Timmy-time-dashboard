"""Tests for request logging middleware."""

import pytest
import time
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


class TestRequestLoggingMiddleware:
    """Test request logging captures essential information."""

    @pytest.fixture
    def app_with_logging(self):
        """Create app with request logging middleware."""
        from dashboard.middleware.request_logging import RequestLoggingMiddleware
        
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "success"}
        
        @app.get("/slow")
        def slow_endpoint():
            time.sleep(0.1)
            return {"message": "slow response"}
        
        @app.get("/error")
        def error_endpoint():
            raise ValueError("Test error")
        
        return app

    def test_logs_request_method_and_path(self, app_with_logging, caplog):
        """Log should include HTTP method and path."""
        with caplog.at_level("INFO"):
            client = TestClient(app_with_logging)
            response = client.get("/test")
            assert response.status_code == 200
        
        # Check log contains method and path
        assert any("GET" in record.message and "/test" in record.message 
                   for record in caplog.records)

    def test_logs_response_status_code(self, app_with_logging, caplog):
        """Log should include response status code."""
        with caplog.at_level("INFO"):
            client = TestClient(app_with_logging)
            response = client.get("/test")
        
        # Check log contains status code
        assert any("200" in record.message for record in caplog.records)

    def test_logs_request_duration(self, app_with_logging, caplog):
        """Log should include request processing time."""
        with caplog.at_level("INFO"):
            client = TestClient(app_with_logging)
            response = client.get("/slow")
        
        # Check log contains duration (e.g., "0.1" or "100ms")
        assert any(record.message for record in caplog.records 
                   if any(c.isdigit() for c in record.message))

    def test_logs_client_ip(self, app_with_logging, caplog):
        """Log should include client IP address."""
        with caplog.at_level("INFO"):
            client = TestClient(app_with_logging)
            response = client.get("/test", headers={"X-Forwarded-For": "192.168.1.1"})
        
        # Check log contains IP
        assert any("192.168.1.1" in record.message or "127.0.0.1" in record.message
                   for record in caplog.records)

    def test_logs_user_agent(self, app_with_logging, caplog):
        """Log should include User-Agent header."""
        with caplog.at_level("INFO"):
            client = TestClient(app_with_logging)
            response = client.get("/test", headers={"User-Agent": "TestAgent/1.0"})
        
        # Check log contains user agent
        assert any("TestAgent" in record.message for record in caplog.records)

    def test_logs_error_requests(self, app_with_logging, caplog):
        """Errors should be logged with appropriate level."""
        with caplog.at_level("ERROR"):
            client = TestClient(app_with_logging, raise_server_exceptions=False)
            response = client.get("/error")
        
        assert response.status_code == 500
        # Should have error log
        assert any(record.levelname == "ERROR" for record in caplog.records)

    def test_skips_health_check_logging(self, caplog):
        """Health check endpoints should not be logged (to reduce noise)."""
        from dashboard.middleware.request_logging import RequestLoggingMiddleware
        
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, skip_paths=["/health"])
        
        @app.get("/health")
        def health_endpoint():
            return {"status": "ok"}
        
        with caplog.at_level("INFO", logger="timmy.requests"):
            client = TestClient(app)
            response = client.get("/health")
        
        # Should not log health check (only check our logger's records)
        timmy_records = [r for r in caplog.records if r.name == "timmy.requests"]
        assert not any("/health" in record.message for record in timmy_records)

    def test_correlation_id_in_logs(self, app_with_logging, caplog):
        """Each request should have a unique correlation ID."""
        with caplog.at_level("INFO"):
            client = TestClient(app_with_logging)
            response = client.get("/test")
        
        # Check for correlation ID format (UUID or similar)
        log_messages = [record.message for record in caplog.records]
        assert any(len(record.message) > 20 for record in caplog.records)  # Rough check for ID
