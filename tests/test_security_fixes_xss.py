import pytest
from fastapi.templating import Jinja2Templates

def test_agent_chat_msg_xss_prevention():
    """Verify XSS prevention in agent_chat_msg.html."""
    templates = Jinja2Templates(directory="src/dashboard/templates")
    payload = "<script>alert('xss')</script>"
    class MockAgent:
        def __init__(self):
            self.name = "TestAgent"
            self.id = "test-agent"
    
    response = templates.get_template("partials/agent_chat_msg.html").render({
        "message": payload,
        "response": payload,
        "error": payload,
        "agent": MockAgent(),
        "timestamp": "12:00:00"
    })
    
    # Check that payload is escaped
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in response
    assert payload not in response

def test_agent_panel_xss_prevention():
    """Verify XSS prevention in agent_panel.html."""
    templates = Jinja2Templates(directory="src/dashboard/templates")
    payload = "<script>alert('xss')</script>"
    class MockAgent:
        def __init__(self):
            self.name = payload
            self.id = "test-agent"
            self.status = "idle"
            self.capabilities = payload
            
    class MockTask:
        def __init__(self):
            self.id = "task-1"
            self.status = type('obj', (object,), {'value': 'completed'})
            self.created_at = "2026-02-26T12:00:00"
            self.description = payload
            self.result = payload

    response = templates.get_template("partials/agent_panel.html").render({
        "agent": MockAgent(),
        "tasks": [MockTask()]
    })
    
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in response
    assert payload not in response

def test_swarm_sidebar_xss_prevention():
    """Verify XSS prevention in swarm_agents_sidebar.html."""
    templates = Jinja2Templates(directory="src/dashboard/templates")
    payload = "<script>alert('xss')</script>"
    class MockAgent:
        def __init__(self):
            self.name = payload
            self.id = "test-agent"
            self.status = "idle"
            self.capabilities = payload
            self.last_seen = "2026-02-26T12:00:00"

    response = templates.get_template("partials/swarm_agents_sidebar.html").render({
        "agents": [MockAgent()]
    })
    
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in response
    assert payload not in response
