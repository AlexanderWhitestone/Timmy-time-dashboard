from unittest.mock import AsyncMock, patch


# ── Index ─────────────────────────────────────────────────────────────────────


def test_index_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200


def test_index_contains_title(client):
    response = client.get("/")
    assert "TIMMY TIME" in response.text


def test_index_contains_chat_interface(client):
    response = client.get("/")
    # Timmy panel loads dynamically via HTMX; verify the trigger attribute is present
    assert 'hx-get="/agents/timmy/panel"' in response.text


# ── Health ────────────────────────────────────────────────────────────────────


def test_health_endpoint_ok(client):
    with patch(
        "dashboard.routes.health.check_ollama",
        new_callable=AsyncMock,
        return_value=True,
    ):
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["services"]["ollama"] == "up"
    assert "agents" in data


def test_health_endpoint_ollama_down(client):
    with patch(
        "dashboard.routes.health.check_ollama",
        new_callable=AsyncMock,
        return_value=False,
    ):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["services"]["ollama"] == "down"


def test_health_status_panel_ollama_up(client):
    with patch(
        "dashboard.routes.health.check_ollama",
        new_callable=AsyncMock,
        return_value=True,
    ):
        response = client.get("/health/status")
    assert response.status_code == 200
    assert "UP" in response.text


def test_health_status_panel_ollama_down(client):
    with patch(
        "dashboard.routes.health.check_ollama",
        new_callable=AsyncMock,
        return_value=False,
    ):
        response = client.get("/health/status")
    assert response.status_code == 200
    assert "DOWN" in response.text


# ── Agents ────────────────────────────────────────────────────────────────────


def test_agents_list(client):
    response = client.get("/agents")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    ids = [a["id"] for a in data["agents"]]
    assert "orchestrator" in ids


def test_agents_list_timmy_metadata(client):
    response = client.get("/agents")
    orch = next(a for a in response.json()["agents"] if a["id"] == "orchestrator")
    assert orch["name"] == "Orchestrator"
    assert orch["model"] == "llama3.1:8b-instruct"
    assert orch["type"] == "local"


# ── Chat ──────────────────────────────────────────────────────────────────────


def test_chat_timmy_success(client):
    with patch(
        "dashboard.routes.agents.timmy_chat",
        return_value="Operational and ready.",
    ):
        response = client.post("/agents/timmy/chat", data={"message": "status?"})

    assert response.status_code == 200
    assert "status?" in response.text
    assert "Operational" in response.text


def test_chat_timmy_shows_user_message(client):
    with patch("dashboard.routes.agents.timmy_chat", return_value="Acknowledged."):
        response = client.post("/agents/timmy/chat", data={"message": "hello there"})

    assert "hello there" in response.text


def test_chat_timmy_ollama_offline(client):
    # Without Ollama, chat returns an error but still shows the user message.
    response = client.post("/agents/timmy/chat", data={"message": "ping"})

    assert response.status_code == 200
    assert "ping" in response.text


def test_chat_timmy_requires_message(client):
    response = client.post("/agents/timmy/chat", data={})
    assert response.status_code == 422


# ── History ────────────────────────────────────────────────────────────────────


def test_history_empty_shows_init_message(client):
    response = client.get("/agents/timmy/history")
    assert response.status_code == 200
    assert "Mission Control initialized" in response.text


def test_history_records_user_and_agent_messages(client):
    with patch("dashboard.routes.agents.timmy_chat", return_value="I am operational."):
        client.post("/agents/timmy/chat", data={"message": "status check"})

    response = client.get("/agents/timmy/history")
    assert "status check" in response.text
    # Queue acknowledgment is NOT logged as an agent message; the real
    # agent response is logged later by the task processor.


def test_history_records_error_when_offline(client):
    # In async mode, if queuing succeeds the user message is recorded
    # and the actual response is logged later by the task processor.
    client.post("/agents/timmy/chat", data={"message": "ping"})

    response = client.get("/agents/timmy/history")
    assert "ping" in response.text


def test_history_clear_resets_to_init_message(client):
    with patch("dashboard.routes.agents.timmy_chat", return_value="Acknowledged."):
        client.post("/agents/timmy/chat", data={"message": "hello"})

    response = client.delete("/agents/timmy/history")
    assert response.status_code == 200
    assert "Mission Control initialized" in response.text


def test_history_empty_after_clear(client):
    with patch("dashboard.routes.agents.timmy_chat", return_value="OK."):
        client.post("/agents/timmy/chat", data={"message": "test"})

    client.delete("/agents/timmy/history")
    response = client.get("/agents/timmy/history")
    assert "test" not in response.text
    assert "Mission Control initialized" in response.text
