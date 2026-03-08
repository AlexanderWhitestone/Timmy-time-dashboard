"""Tests for the Work Orders API endpoints."""


def test_work_orders_page_returns_200(client):
    response = client.get("/work-orders/queue")
    assert response.status_code == 200
    assert "WORK ORDERS" in response.text


def test_submit_work_order(client):
    """POST /work-orders/submit creates a work order."""
    response = client.post("/work-orders/submit", data={
        "title": "Fix the dashboard",
        "description": "Details here",
        "priority": "high",
        "category": "bug",
        "submitter": "dashboard",
        "related_files": "src/app.py",
    })
    assert response.status_code == 200


def test_pending_partial_returns_200(client):
    """GET /work-orders/queue/pending returns HTML."""
    response = client.get("/work-orders/queue/pending")
    assert response.status_code == 200


def test_active_partial_returns_200(client):
    """GET /work-orders/queue/active returns HTML."""
    response = client.get("/work-orders/queue/active")
    assert response.status_code == 200


def test_submit_and_list_roundtrip(client):
    """Submitting a work order makes it appear in the pending section."""
    client.post("/work-orders/submit", data={
        "title": "Roundtrip WO",
        "priority": "medium",
        "category": "suggestion",
        "submitter": "test",
    })
    response = client.get("/work-orders/queue/pending")
    assert "Roundtrip WO" in response.text


def test_approve_work_order(client):
    """POST /work-orders/{id}/approve changes status."""
    # Submit one first
    client.post("/work-orders/submit", data={
        "title": "To approve",
        "priority": "medium",
        "category": "suggestion",
        "submitter": "test",
    })
    # Get ID from pending
    pending = client.get("/work-orders/queue/pending")
    import re
    match = re.search(r'id="wo-([^"]+)"', pending.text)
    if match:
        wo_id = match.group(1)
        response = client.post(f"/work-orders/{wo_id}/approve")
        assert response.status_code == 200
        assert "APPROVED" in response.text.upper() or "EXECUTE" in response.text.upper()
