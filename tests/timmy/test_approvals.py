"""Tests for timmy.approvals — approval workflow and Golden Timmy rule."""

import pytest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from timmy.approvals import (
    GOLDEN_TIMMY,
    ApprovalItem,
    create_item,
    list_pending,
    list_all,
    get_item,
    approve,
    reject,
    expire_old,
    _get_conn,
)


@pytest.fixture
def db_path(tmp_path):
    """Fresh SQLite DB for each test."""
    return tmp_path / "test_approvals.db"


class TestGoldenTimmy:
    """Test the Golden Timmy constant."""

    def test_golden_timmy_default_true(self):
        assert GOLDEN_TIMMY is True


class TestApprovalItem:
    """Test ApprovalItem dataclass."""

    def test_create(self):
        item = ApprovalItem(
            id="test-id",
            title="Deploy update",
            description="Deploy v2.0 to production",
            proposed_action="git push && deploy",
            impact="high",
            created_at=datetime.now(timezone.utc),
            status="pending",
        )
        assert item.id == "test-id"
        assert item.status == "pending"
        assert item.impact == "high"


class TestCreateItem:
    """Test create_item persistence."""

    def test_create_and_retrieve(self, db_path):
        item = create_item(
            title="Test approval",
            description="A test action",
            proposed_action="run tests",
            impact="low",
            db_path=db_path,
        )
        assert item.id  # UUID generated
        assert item.status == "pending"
        assert item.title == "Test approval"

        # Retrieve it
        retrieved = get_item(item.id, db_path)
        assert retrieved is not None
        assert retrieved.id == item.id
        assert retrieved.title == "Test approval"

    def test_create_default_impact(self, db_path):
        item = create_item(
            title="T",
            description="D",
            proposed_action="A",
            db_path=db_path,
        )
        assert item.impact == "low"


class TestListPending:
    """Test list_pending."""

    def test_empty_db(self, db_path):
        items = list_pending(db_path)
        assert items == []

    def test_only_pending(self, db_path):
        item1 = create_item("A", "D", "A", db_path=db_path)
        item2 = create_item("B", "D", "A", db_path=db_path)
        approve(item1.id, db_path)

        pending = list_pending(db_path)
        assert len(pending) == 1
        assert pending[0].id == item2.id

    def test_ordered_newest_first(self, db_path):
        item1 = create_item("First", "D", "A", db_path=db_path)
        item2 = create_item("Second", "D", "A", db_path=db_path)

        pending = list_pending(db_path)
        assert pending[0].title == "Second"


class TestListAll:
    """Test list_all."""

    def test_includes_all_statuses(self, db_path):
        item1 = create_item("A", "D", "A", db_path=db_path)
        item2 = create_item("B", "D", "A", db_path=db_path)
        approve(item1.id, db_path)
        reject(item2.id, db_path)

        all_items = list_all(db_path)
        assert len(all_items) == 2


class TestApproveReject:
    """Test approve and reject operations."""

    def test_approve_item(self, db_path):
        item = create_item("T", "D", "A", db_path=db_path)
        result = approve(item.id, db_path)
        assert result.status == "approved"

    def test_reject_item(self, db_path):
        item = create_item("T", "D", "A", db_path=db_path)
        result = reject(item.id, db_path)
        assert result.status == "rejected"

    def test_get_nonexistent_returns_none(self, db_path):
        result = get_item("nonexistent-id", db_path)
        assert result is None


class TestExpireOld:
    """Test expire_old cleanup."""

    def test_expire_removes_old_pending(self, db_path):
        # Create item and manually backdate it
        item = create_item("Old", "D", "A", db_path=db_path)

        conn = _get_conn(db_path)
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        conn.execute(
            "UPDATE approval_items SET created_at = ? WHERE id = ?",
            (old_date, item.id),
        )
        conn.commit()
        conn.close()

        count = expire_old(db_path)
        assert count == 1

        # Should be gone
        assert get_item(item.id, db_path) is None

    def test_expire_keeps_recent(self, db_path):
        create_item("Recent", "D", "A", db_path=db_path)

        count = expire_old(db_path)
        assert count == 0
        assert len(list_pending(db_path)) == 1

    def test_expire_keeps_approved(self, db_path):
        item = create_item("Approved", "D", "A", db_path=db_path)
        approve(item.id, db_path)

        # Backdate it
        conn = _get_conn(db_path)
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        conn.execute(
            "UPDATE approval_items SET created_at = ? WHERE id = ?",
            (old_date, item.id),
        )
        conn.commit()
        conn.close()

        count = expire_old(db_path)
        assert count == 0  # approved items not expired
