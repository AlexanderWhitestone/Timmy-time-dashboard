"""Tests for the work order system."""

from work_orders.models import (
    WorkOrder,
    WorkOrderCategory,
    WorkOrderPriority,
    WorkOrderStatus,
    create_work_order,
    get_counts_by_status,
    get_pending_count,
    get_work_order,
    list_work_orders,
    update_work_order_status,
)
from work_orders.risk import compute_risk_score, should_auto_execute


# ── Model CRUD tests ──────────────────────────────────────────────────────────


def test_create_work_order():
    wo = create_work_order(
        title="Fix the login bug",
        description="Login fails on mobile",
        priority="high",
        category="bug",
        submitter="comet",
    )
    assert wo.id
    assert wo.title == "Fix the login bug"
    assert wo.priority == WorkOrderPriority.HIGH
    assert wo.category == WorkOrderCategory.BUG
    assert wo.status == WorkOrderStatus.SUBMITTED
    assert wo.submitter == "comet"


def test_get_work_order():
    wo = create_work_order(title="Test get", submitter="test")
    fetched = get_work_order(wo.id)
    assert fetched is not None
    assert fetched.title == "Test get"
    assert fetched.submitter == "test"


def test_get_work_order_not_found():
    assert get_work_order("nonexistent-id") is None


def test_list_work_orders_no_filter():
    create_work_order(title="Order A", submitter="a")
    create_work_order(title="Order B", submitter="b")
    orders = list_work_orders()
    assert len(orders) >= 2


def test_list_work_orders_by_status():
    wo = create_work_order(title="Status test")
    update_work_order_status(wo.id, WorkOrderStatus.APPROVED)
    approved = list_work_orders(status=WorkOrderStatus.APPROVED)
    assert any(o.id == wo.id for o in approved)


def test_list_work_orders_by_priority():
    create_work_order(title="Critical item", priority="critical")
    critical = list_work_orders(priority=WorkOrderPriority.CRITICAL)
    assert len(critical) >= 1
    assert all(o.priority == WorkOrderPriority.CRITICAL for o in critical)


def test_update_work_order_status():
    wo = create_work_order(title="Update test")
    updated = update_work_order_status(wo.id, WorkOrderStatus.APPROVED)
    assert updated is not None
    assert updated.status == WorkOrderStatus.APPROVED
    assert updated.approved_at is not None


def test_update_work_order_with_kwargs():
    wo = create_work_order(title="Kwargs test")
    updated = update_work_order_status(
        wo.id, WorkOrderStatus.REJECTED, rejection_reason="Not needed"
    )
    assert updated is not None
    assert updated.rejection_reason == "Not needed"


def test_update_nonexistent():
    result = update_work_order_status("fake-id", WorkOrderStatus.APPROVED)
    assert result is None


def test_get_pending_count():
    create_work_order(title="Pending 1")
    create_work_order(title="Pending 2")
    count = get_pending_count()
    assert count >= 2


def test_get_counts_by_status():
    create_work_order(title="Count test")
    counts = get_counts_by_status()
    assert "submitted" in counts
    assert counts["submitted"] >= 1


def test_related_files_roundtrip():
    wo = create_work_order(
        title="Files test",
        related_files=["src/config.py", "src/timmy/agent.py"],
    )
    fetched = get_work_order(wo.id)
    assert fetched.related_files == ["src/config.py", "src/timmy/agent.py"]


# ── Risk scoring tests ────────────────────────────────────────────────────────


def test_risk_score_low_suggestion():
    wo = WorkOrder(
        priority=WorkOrderPriority.LOW,
        category=WorkOrderCategory.SUGGESTION,
    )
    score = compute_risk_score(wo)
    assert score == 2  # 1 (low) + 1 (suggestion)


def test_risk_score_critical_bug():
    wo = WorkOrder(
        priority=WorkOrderPriority.CRITICAL,
        category=WorkOrderCategory.BUG,
    )
    score = compute_risk_score(wo)
    assert score == 7  # 4 (critical) + 3 (bug)


def test_risk_score_sensitive_files():
    wo = WorkOrder(
        priority=WorkOrderPriority.LOW,
        category=WorkOrderCategory.SUGGESTION,
        related_files=["src/swarm/coordinator.py"],
    )
    score = compute_risk_score(wo)
    assert score == 4  # 1 + 1 + 2 (sensitive)


def test_should_auto_execute_disabled(monkeypatch):
    monkeypatch.setattr("config.settings.work_orders_auto_execute", False)
    wo = WorkOrder(
        priority=WorkOrderPriority.LOW,
        category=WorkOrderCategory.SUGGESTION,
    )
    assert should_auto_execute(wo) is False


def test_should_auto_execute_low_risk(monkeypatch):
    monkeypatch.setattr("config.settings.work_orders_auto_execute", True)
    monkeypatch.setattr("config.settings.work_orders_auto_threshold", "low")
    wo = WorkOrder(
        priority=WorkOrderPriority.LOW,
        category=WorkOrderCategory.SUGGESTION,
    )
    assert should_auto_execute(wo) is True


def test_should_auto_execute_high_priority_blocked(monkeypatch):
    monkeypatch.setattr("config.settings.work_orders_auto_execute", True)
    monkeypatch.setattr("config.settings.work_orders_auto_threshold", "low")
    wo = WorkOrder(
        priority=WorkOrderPriority.HIGH,
        category=WorkOrderCategory.BUG,
    )
    assert should_auto_execute(wo) is False


# ── Route tests ───────────────────────────────────────────────────────────────


def test_submit_work_order(client):
    resp = client.post(
        "/work-orders/submit",
        data={
            "title": "Test submission",
            "description": "Testing the API",
            "priority": "low",
            "category": "suggestion",
            "submitter": "test-agent",
            "submitter_type": "agent",
            "related_files": "",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["work_order_id"]
    assert data["execution_mode"] in ("auto", "manual")


def test_submit_json(client):
    resp = client.post(
        "/work-orders/submit/json",
        json={
            "title": "JSON test",
            "description": "Testing JSON API",
            "priority": "medium",
            "category": "improvement",
            "submitter": "comet",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


def test_list_work_orders_route(client):
    client.post(
        "/work-orders/submit",
        data={"title": "List test", "submitter": "test"},
    )
    resp = client.get("/work-orders")
    assert resp.status_code == 200
    data = resp.json()
    assert "work_orders" in data
    assert data["count"] >= 1


def test_get_work_order_route(client):
    submit = client.post(
        "/work-orders/submit",
        data={"title": "Get test", "submitter": "test"},
    )
    wo_id = submit.json()["work_order_id"]
    resp = client.get(f"/work-orders/{wo_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Get test"


def test_get_work_order_not_found_route(client):
    resp = client.get("/work-orders/nonexistent-id")
    assert resp.status_code == 404


def test_approve_work_order(client):
    submit = client.post(
        "/work-orders/submit",
        data={"title": "Approve test", "submitter": "test"},
    )
    wo_id = submit.json()["work_order_id"]
    resp = client.post(f"/work-orders/{wo_id}/approve")
    assert resp.status_code == 200


def test_reject_work_order(client):
    submit = client.post(
        "/work-orders/submit",
        data={"title": "Reject test", "submitter": "test"},
    )
    wo_id = submit.json()["work_order_id"]
    resp = client.post(
        f"/work-orders/{wo_id}/reject",
        data={"reason": "Not needed"},
    )
    assert resp.status_code == 200


def test_work_order_counts(client):
    client.post(
        "/work-orders/submit",
        data={"title": "Count test", "submitter": "test"},
    )
    resp = client.get("/work-orders/api/counts")
    assert resp.status_code == 200
    data = resp.json()
    assert "pending" in data
    assert "total" in data


def test_work_order_queue_page(client):
    resp = client.get("/work-orders/queue")
    assert resp.status_code == 200
    assert b"WORK ORDERS" in resp.content


def test_work_order_pending_partial(client):
    resp = client.get("/work-orders/queue/pending")
    assert resp.status_code == 200
