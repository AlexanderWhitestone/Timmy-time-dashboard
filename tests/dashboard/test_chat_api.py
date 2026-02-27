"""Tests for the JSON chat API (/api/chat, /api/upload, /api/chat/history)."""

import io
from unittest.mock import patch


# ── POST /api/chat ────────────────────────────────────────────────────────────


def test_api_chat_success(client):
    with patch("dashboard.routes.chat_api.timmy_chat", return_value="Hello from Timmy."):
        response = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "Hello from Timmy."
    assert "timestamp" in data


def test_api_chat_multimodal_content(client):
    """Multimodal content arrays should extract text parts."""
    with patch("dashboard.routes.chat_api.timmy_chat", return_value="I see an image."):
        response = client.post(
            "/api/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What is this?"},
                            {"type": "image_url", "image_url": {"url": "/uploads/test.jpg"}},
                        ],
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["reply"] == "I see an image."


def test_api_chat_empty_messages(client):
    response = client.post("/api/chat", json={"messages": []})
    assert response.status_code == 400
    assert "error" in response.json()


def test_api_chat_missing_messages(client):
    response = client.post("/api/chat", json={"foo": "bar"})
    assert response.status_code == 400
    assert "messages" in response.json()["error"]


def test_api_chat_no_user_message(client):
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "assistant", "content": "hi"}]},
    )
    assert response.status_code == 400
    assert "No user message" in response.json()["error"]


def test_api_chat_ollama_offline(client):
    with patch(
        "dashboard.routes.chat_api.timmy_chat",
        side_effect=ConnectionError("Ollama unreachable"),
    ):
        response = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 503
    data = response.json()
    assert "offline" in data["error"].lower() or "unreachable" in data["error"].lower()


def test_api_chat_logs_to_message_log(client):
    from dashboard.store import message_log

    with patch("dashboard.routes.chat_api.timmy_chat", return_value="Reply."):
        client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "test msg"}]},
        )

    entries = message_log.all()
    assert len(entries) == 2
    assert entries[0].role == "user"
    assert entries[0].content == "test msg"
    assert entries[1].role == "agent"
    assert entries[1].content == "Reply."


def test_api_chat_invalid_json(client):
    response = client.post(
        "/api/chat",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400


# ── POST /api/upload ──────────────────────────────────────────────────────────


def test_api_upload_file(client, tmp_path):
    with patch("dashboard.routes.chat_api._UPLOAD_DIR", str(tmp_path)):
        response = client.post(
            "/api/upload",
            files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["fileName"] == "test.txt"
    assert data["mimeType"] == "text/plain"
    assert "/uploads/" in data["url"]


def test_api_upload_image(client, tmp_path):
    # 1x1 red PNG
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    )
    with patch("dashboard.routes.chat_api._UPLOAD_DIR", str(tmp_path)):
        response = client.post(
            "/api/upload",
            files={"file": ("photo.png", io.BytesIO(png), "image/png")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["fileName"] == "photo.png"
    assert data["mimeType"] == "image/png"


# ── GET /api/chat/history ────────────────────────────────────────────────────


def test_api_chat_history_empty(client):
    response = client.get("/api/chat/history")
    assert response.status_code == 200
    assert response.json()["messages"] == []


def test_api_chat_history_after_chat(client):
    with patch("dashboard.routes.chat_api.timmy_chat", return_value="Hi!"):
        client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    response = client.get("/api/chat/history")
    assert response.status_code == 200
    msgs = response.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "agent"


# ── DELETE /api/chat/history ──────────────────────────────────────────────────


def test_api_clear_history(client):
    from dashboard.store import message_log

    message_log.append(role="user", content="old", timestamp="00:00:00")

    response = client.delete("/api/chat/history")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert len(message_log) == 0
