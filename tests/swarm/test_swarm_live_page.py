"""Tests for the GET /swarm/live page route."""


class TestSwarmLivePage:
    def test_swarm_live_returns_html(self, client):
        resp = client.get("/swarm/live")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_swarm_live_contains_dashboard_title(self, client):
        resp = client.get("/swarm/live")
        assert "LIVE SWARM" in resp.text

    def test_swarm_live_contains_websocket_script(self, client):
        resp = client.get("/swarm/live")
        assert "/swarm/live" in resp.text
        assert "WebSocket" in resp.text

    def test_swarm_live_contains_stat_elements(self, client):
        resp = client.get("/swarm/live")
        assert "stat-agents" in resp.text
        assert "stat-active" in resp.text
        assert "stat-tasks" in resp.text
