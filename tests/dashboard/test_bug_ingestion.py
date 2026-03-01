"""Tests for bug report ingestion pipeline.

TDD — these tests are written FIRST, before the implementation.
Tests cover:
  1. POST /api/bugs/submit endpoint
  2. handle_bug_report handler with decision trail
  3. CLI ingest-report command
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Point task_queue and event_log SQLite to a temp directory."""
    db = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.task_queue.models.DB_PATH", db)
    monkeypatch.setattr("swarm.event_log.DB_PATH", db)


@pytest.fixture
def client():
    from dashboard.app import app

    with TestClient(app) as c:
        yield c


# ── Sample data ──────────────────────────────────────────────────────────


def _sample_report(bugs=None):
    """Build a minimal test report."""
    if bugs is None:
        bugs = [{"title": "Test bug", "severity": "P1", "description": "Something broke"}]
    return {"reporter": "comet", "bugs": bugs}


def _sample_bug(**overrides):
    """Build a single bug entry with defaults."""
    bug = {
        "title": "Widget crashes on click",
        "severity": "P0",
        "description": "Clicking the save button crashes the app",
    }
    bug.update(overrides)
    return bug


# ── Test Group 1: Bug Submission Endpoint ────────────────────────────────


class TestBugSubmitEndpoint:

    def test_submit_single_bug(self, client):
        """POST one bug creates one bug_report task."""
        resp = client.post("/api/bugs/submit", json=_sample_report())
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 1
        assert len(data["task_ids"]) == 1

    def test_submit_multiple_bugs(self, client):
        """POST 3 bugs creates 3 tasks."""
        bugs = [
            _sample_bug(title="Bug A", severity="P0"),
            _sample_bug(title="Bug B", severity="P1"),
            _sample_bug(title="Bug C", severity="P2"),
        ]
        resp = client.post("/api/bugs/submit", json=_sample_report(bugs))
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 3
        assert len(data["task_ids"]) == 3

    def test_submit_maps_severity_to_priority(self, client):
        """P0→urgent, P1→high, P2→normal."""
        from swarm.task_queue.models import get_task

        bugs = [
            _sample_bug(title="P0 bug", severity="P0"),
            _sample_bug(title="P1 bug", severity="P1"),
            _sample_bug(title="P2 bug", severity="P2"),
        ]
        resp = client.post("/api/bugs/submit", json=_sample_report(bugs))
        data = resp.json()

        tasks = [get_task(tid) for tid in data["task_ids"]]
        priorities = {t.title: t.priority.value for t in tasks}

        assert priorities["[P0] P0 bug"] == "urgent"
        assert priorities["[P1] P1 bug"] == "high"
        assert priorities["[P2] P2 bug"] == "normal"

    def test_submit_formats_description(self, client):
        """Evidence, root_cause, fix_options appear in task description."""
        from swarm.task_queue.models import get_task

        bug = _sample_bug(
            evidence="Console shows null pointer",
            root_cause="Missing null check in handler",
            fix_options=["Add guard clause", "Use optional chaining"],
        )
        resp = client.post("/api/bugs/submit", json=_sample_report([bug]))
        data = resp.json()

        task = get_task(data["task_ids"][0])
        assert "Console shows null pointer" in task.description
        assert "Missing null check" in task.description
        assert "Add guard clause" in task.description

    def test_submit_sets_task_type(self, client):
        """Created tasks have task_type='bug_report'."""
        from swarm.task_queue.models import get_task

        resp = client.post("/api/bugs/submit", json=_sample_report())
        data = resp.json()

        task = get_task(data["task_ids"][0])
        assert task.task_type == "bug_report"

    def test_submit_rejects_empty_bugs(self, client):
        """400 when bugs array is empty."""
        resp = client.post("/api/bugs/submit", json=_sample_report(bugs=[]))
        assert resp.status_code == 400

    def test_submit_rejects_missing_fields(self, client):
        """400 when required fields are missing."""
        resp = client.post("/api/bugs/submit", json={"reporter": "comet", "bugs": [{"title": "x"}]})
        assert resp.status_code == 400

    def test_submit_records_reporter(self, client):
        """Task created_by reflects the reporter."""
        from swarm.task_queue.models import get_task

        resp = client.post("/api/bugs/submit", json=_sample_report())
        data = resp.json()

        task = get_task(data["task_ids"][0])
        assert task.created_by == "comet"


# ── Test Group 2: Bug Report Handler + Decision Trail ────────────────────


class TestBugReportHandler:

    def _make_task(self, **overrides):
        """Create a real bug_report task in the queue."""
        from swarm.task_queue.models import create_task

        defaults = {
            "title": "[P0] Widget crash",
            "description": "The widget crashes when clicked",
            "task_type": "bug_report",
            "priority": "urgent",
            "created_by": "comet",
        }
        defaults.update(overrides)
        return create_task(**defaults)

    def _get_handler(self):
        """Import the handle_bug_report function directly."""
        from dashboard.app import handle_bug_report

        return handle_bug_report

    def test_handler_dispatches_fix_to_forge(self):
        """Handler creates a code_fix task assigned to Forge."""
        from swarm.task_queue.models import get_task, list_tasks

        handler = self._get_handler()
        task = self._make_task()
        result = handler(task)

        # Should mention Forge dispatch
        assert "Forge" in result
        assert "Fix dispatched" in result

        # A code_fix task should exist assigned to forge
        all_tasks = list_tasks()
        fix_tasks = [t for t in all_tasks if t.task_type == "code_fix" and t.assigned_to == "forge"]
        assert len(fix_tasks) == 1
        fix = fix_tasks[0]
        assert fix.title == f"[Fix] {task.title}"
        assert fix.created_by == "timmy"
        assert fix.parent_task_id == task.id

    def test_handler_logs_decision_to_event_log(self):
        """Handler logs a decision entry to the event log."""
        handler = self._get_handler()
        task = self._make_task()
        handler(task)

        from swarm.event_log import EventType, list_events

        events = list_events(event_type=EventType.BUG_REPORT_CREATED, task_id=task.id)
        assert len(events) >= 1

        decision = json.loads(events[0].data)
        assert decision["action"] == "dispatch_to_forge"
        assert decision["outcome"] == "fix_dispatched"
        assert "fix_task_id" in decision

    def test_handler_fix_task_links_to_bug(self):
        """Fix task has parent_task_id pointing to the original bug."""
        from swarm.task_queue.models import get_task

        handler = self._get_handler()
        task = self._make_task()
        handler(task)

        from swarm.event_log import EventType, list_events

        events = list_events(event_type=EventType.BUG_REPORT_CREATED, task_id=task.id)
        decision = json.loads(events[0].data)
        fix_task = get_task(decision["fix_task_id"])

        assert fix_task.parent_task_id == task.id
        assert fix_task.task_type == "code_fix"

    def test_handler_graceful_fallback_on_dispatch_failure(self):
        """When create_task fails, handler still returns a result and logs the error."""
        handler = self._get_handler()
        task = self._make_task()  # Create task before patching

        # Patch only the handler's dispatch call (re-imported inside the function body)
        with patch("swarm.task_queue.models.create_task", side_effect=RuntimeError("db locked")):
            result = handler(task)

        assert result is not None
        assert "dispatch failed" in result.lower()

        from swarm.event_log import EventType, list_events

        events = list_events(event_type=EventType.BUG_REPORT_CREATED, task_id=task.id)
        assert len(events) >= 1
        decision = json.loads(events[0].data)
        assert decision["outcome"] == "dispatch_failed"
        assert "db locked" in decision.get("error", "")

    def test_handler_decision_includes_reason(self):
        """Decision dict always has action, reason, priority, outcome."""
        handler = self._get_handler()
        task = self._make_task()
        handler(task)

        from swarm.event_log import EventType, list_events

        events = list_events(event_type=EventType.BUG_REPORT_CREATED, task_id=task.id)
        decision = json.loads(events[0].data)

        assert "action" in decision
        assert "reason" in decision
        assert "priority" in decision
        assert "outcome" in decision

    def test_handler_result_is_not_just_acknowledged(self):
        """task.result should contain structured info, not just 'acknowledged'."""
        handler = self._get_handler()
        task = self._make_task()
        result = handler(task)

        assert "acknowledged" not in result.lower() or "Decision" in result


# ── Test Group 3: CLI Command ────────────────────────────────────────────


class TestIngestReportCLI:

    def test_cli_ingest_from_file(self, tmp_path):
        """CLI reads a JSON file and creates tasks."""
        from typer.testing import CliRunner
        from timmy.cli import app

        report = _sample_report([
            _sample_bug(title="CLI Bug A", severity="P1"),
            _sample_bug(title="CLI Bug B", severity="P2"),
        ])
        report_file = tmp_path / "report.json"
        report_file.write_text(json.dumps(report))

        runner = CliRunner()
        result = runner.invoke(app, ["ingest-report", str(report_file)])

        assert result.exit_code == 0
        assert "2" in result.stdout  # 2 bugs created

    def test_cli_dry_run(self, tmp_path):
        """--dry-run shows bugs but creates nothing."""
        from typer.testing import CliRunner
        from timmy.cli import app
        from swarm.task_queue.models import list_tasks

        report = _sample_report([_sample_bug(title="Dry Run Bug")])
        report_file = tmp_path / "report.json"
        report_file.write_text(json.dumps(report))

        runner = CliRunner()
        result = runner.invoke(app, ["ingest-report", "--dry-run", str(report_file)])

        assert result.exit_code == 0
        assert "dry run" in result.stdout.lower()

        # No tasks should have been created
        tasks = list_tasks()
        bug_tasks = [t for t in tasks if t.task_type == "bug_report" and "Dry Run" in t.title]
        assert len(bug_tasks) == 0

    def test_cli_invalid_json(self, tmp_path):
        """CLI exits with error on invalid JSON."""
        from typer.testing import CliRunner
        from timmy.cli import app

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json {{{")

        runner = CliRunner()
        result = runner.invoke(app, ["ingest-report", str(bad_file)])

        assert result.exit_code != 0

    def test_cli_missing_file(self):
        """CLI exits with error when file doesn't exist."""
        from typer.testing import CliRunner
        from timmy.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["ingest-report", "/nonexistent/file.json"])

        assert result.exit_code != 0
