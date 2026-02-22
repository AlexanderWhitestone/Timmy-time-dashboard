"""Tests for timmy/approvals.py — governance layer."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from timmy.approvals import (
    GOLDEN_TIMMY,
    ApprovalItem,
    approve,
    create_item,
    expire_old,
    get_item,
    list_all,
    list_pending,
    reject,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """A fresh per-test SQLite DB so tests are isolated."""
    return tmp_path / "test_approvals.db"


# ---------------------------------------------------------------------------
# GOLDEN_TIMMY constant
# ---------------------------------------------------------------------------

def test_golden_timmy_is_true():
    """GOLDEN_TIMMY must default to True — the governance foundation."""
    assert GOLDEN_TIMMY is True


# ---------------------------------------------------------------------------
# ApprovalItem creation
# ---------------------------------------------------------------------------

def test_create_item_returns_pending(tmp_db):
    item = create_item("Deploy new model", "Update Ollama model", "pull llama3.3", impact="medium", db_path=tmp_db)
    assert item.status == "pending"
    assert item.title == "Deploy new model"
    assert item.impact == "medium"
    assert isinstance(item.id, str) and len(item.id) > 0
    assert isinstance(item.created_at, datetime)


def test_create_item_default_impact_is_low(tmp_db):
    item = create_item("Minor task", "desc", "do thing", db_path=tmp_db)
    assert item.impact == "low"


def test_create_item_persists_across_calls(tmp_db):
    item = create_item("Persistent task", "persists", "action", db_path=tmp_db)
    fetched = get_item(item.id, db_path=tmp_db)
    assert fetched is not None
    assert fetched.id == item.id
    assert fetched.title == "Persistent task"


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_pending_returns_only_pending(tmp_db):
    item1 = create_item("Task A", "desc", "action A", db_path=tmp_db)
    item2 = create_item("Task B", "desc", "action B", db_path=tmp_db)
    approve(item1.id, db_path=tmp_db)

    pending = list_pending(db_path=tmp_db)
    ids = [i.id for i in pending]
    assert item2.id in ids
    assert item1.id not in ids


def test_list_all_includes_all_statuses(tmp_db):
    item1 = create_item("Task A", "d", "a", db_path=tmp_db)
    item2 = create_item("Task B", "d", "b", db_path=tmp_db)
    approve(item1.id, db_path=tmp_db)
    reject(item2.id, db_path=tmp_db)

    all_items = list_all(db_path=tmp_db)
    statuses = {i.status for i in all_items}
    assert "approved" in statuses
    assert "rejected" in statuses


def test_list_pending_empty_on_fresh_db(tmp_db):
    assert list_pending(db_path=tmp_db) == []


# ---------------------------------------------------------------------------
# Approve / Reject
# ---------------------------------------------------------------------------

def test_approve_changes_status(tmp_db):
    item = create_item("Approve me", "desc", "act", db_path=tmp_db)
    updated = approve(item.id, db_path=tmp_db)
    assert updated is not None
    assert updated.status == "approved"


def test_reject_changes_status(tmp_db):
    item = create_item("Reject me", "desc", "act", db_path=tmp_db)
    updated = reject(item.id, db_path=tmp_db)
    assert updated is not None
    assert updated.status == "rejected"


def test_approve_nonexistent_returns_none(tmp_db):
    result = approve("not-a-real-id", db_path=tmp_db)
    assert result is None


def test_reject_nonexistent_returns_none(tmp_db):
    result = reject("not-a-real-id", db_path=tmp_db)
    assert result is None


# ---------------------------------------------------------------------------
# Get item
# ---------------------------------------------------------------------------

def test_get_item_returns_correct_item(tmp_db):
    item = create_item("Get me", "d", "a", db_path=tmp_db)
    fetched = get_item(item.id, db_path=tmp_db)
    assert fetched is not None
    assert fetched.id == item.id
    assert fetched.title == "Get me"


def test_get_item_nonexistent_returns_none(tmp_db):
    assert get_item("ghost-id", db_path=tmp_db) is None


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def test_expire_old_removes_stale_pending(tmp_db):
    """Items created long before the cutoff should be expired."""
    import sqlite3
    from timmy.approvals import _get_conn

    item = create_item("Old item", "d", "a", db_path=tmp_db)

    # Backdate the created_at to 8 days ago
    old_ts = (datetime.now(timezone.utc).replace(year=2020)).isoformat()
    conn = _get_conn(tmp_db)
    conn.execute("UPDATE approval_items SET created_at = ? WHERE id = ?", (old_ts, item.id))
    conn.commit()
    conn.close()

    removed = expire_old(db_path=tmp_db)
    assert removed == 1
    assert get_item(item.id, db_path=tmp_db) is None


def test_expire_old_keeps_actioned_items(tmp_db):
    """Approved/rejected items should NOT be expired."""
    import sqlite3
    from timmy.approvals import _get_conn

    item = create_item("Actioned item", "d", "a", db_path=tmp_db)
    approve(item.id, db_path=tmp_db)

    # Backdate
    old_ts = (datetime.now(timezone.utc).replace(year=2020)).isoformat()
    conn = _get_conn(tmp_db)
    conn.execute("UPDATE approval_items SET created_at = ? WHERE id = ?", (old_ts, item.id))
    conn.commit()
    conn.close()

    removed = expire_old(db_path=tmp_db)
    assert removed == 0
    assert get_item(item.id, db_path=tmp_db) is not None


def test_expire_old_returns_zero_when_nothing_to_expire(tmp_db):
    create_item("Fresh item", "d", "a", db_path=tmp_db)
    removed = expire_old(db_path=tmp_db)
    assert removed == 0


# ---------------------------------------------------------------------------
# Multiple items ordering
# ---------------------------------------------------------------------------

def test_list_pending_newest_first(tmp_db):
    item1 = create_item("First", "d", "a", db_path=tmp_db)
    item2 = create_item("Second", "d", "b", db_path=tmp_db)
    pending = list_pending(db_path=tmp_db)
    # Most recently created should appear first
    assert pending[0].id == item2.id
    assert pending[1].id == item1.id
