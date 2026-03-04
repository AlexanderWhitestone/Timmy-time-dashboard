import pytest
from fastapi.testclient import TestClient
from dashboard.app import app
from config import settings
import html

@pytest.fixture
def client():
    return TestClient(app)

def test_health_status_xss_vulnerability(client):
    """Verify that the health status page escapes the model name."""
    original_model = settings.ollama_model
    malicious_model = '"><script>alert("XSS")</script>'
    
    try:
        # Inject malicious model name into settings
        settings.ollama_model = malicious_model
        
        response = client.get("/health/status")
        assert response.status_code == 200
        
        # The malicious script should be escaped
        escaped_model = html.escape(malicious_model)
        assert escaped_model in response.text
        assert malicious_model not in response.text
    finally:
        settings.ollama_model = original_model

def test_grok_toggle_xss_vulnerability(client):
    """Verify that the grok toggle card escapes the model name."""
    original_model = settings.grok_default_model
    malicious_model = '"><img src=x onerror=alert(1)>'
    
    try:
        # Inject malicious model name into settings
        settings.grok_default_model = malicious_model
        
        # We need to make grok available to trigger the render_toggle_card
        # Since we're in test mode, we might need to mock this or just call the function
        from dashboard.routes.grok import _render_toggle_card
        
        html_output = _render_toggle_card(active=True)
        
        # The malicious script should be escaped
        escaped_model = html.escape(malicious_model)
        assert escaped_model in html_output
        assert malicious_model not in html_output
    finally:
        settings.grok_default_model = original_model
