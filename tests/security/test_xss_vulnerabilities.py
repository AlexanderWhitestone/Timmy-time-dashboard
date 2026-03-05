import pytest
from fastapi.testclient import TestClient
from dashboard.app import app
import html

@pytest.fixture
def client():
    return TestClient(app)

def test_health_status_xss_vulnerability(client, monkeypatch):
    """Verify that the health status page escapes the model name."""
    malicious_model = '"><script>alert("XSS")</script>'
    monkeypatch.setattr("config.settings.ollama_model", malicious_model)

    response = client.get("/health/status")
    assert response.status_code == 200

    escaped_model = html.escape(malicious_model)
    assert escaped_model in response.text
    assert malicious_model not in response.text

def test_grok_toggle_xss_vulnerability(client, monkeypatch):
    """Verify that the grok toggle card escapes the model name."""
    malicious_model = '"><img src=x onerror=alert(1)>'
    monkeypatch.setattr("config.settings.grok_default_model", malicious_model)

    from dashboard.routes.grok import _render_toggle_card

    html_output = _render_toggle_card(active=True)

    escaped_model = html.escape(malicious_model)
    assert escaped_model in html_output
    assert malicious_model not in html_output
