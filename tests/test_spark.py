"""Tests for the Spark Intelligence integration.

Covers:
- spark.memory: event capture, memory consolidation, importance scoring
- spark.eidos: predictions, evaluations, accuracy stats
- spark.advisor: advisory generation from patterns
- spark.engine: top-level engine wiring all subsystems
- dashboard.routes.spark: HTTP endpoints
"""

import json
from pathlib import Path

import pytest


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_spark_db(tmp_path, monkeypatch):
    """Redirect all Spark SQLite writes to a temp directory."""
    db_path = tmp_path / "spark.db"
    monkeypatch.setattr("spark.memory.DB_PATH", db_path)
    monkeypatch.setattr("spark.eidos.DB_PATH", db_path)
    yield db_path


# ── spark.memory ────────────────────────────────────────────────────────────


class TestImportanceScoring:
    def test_failure_scores_high(self):
        from spark.memory import score_importance
        score = score_importance("task_failed", {})
        assert score >= 0.9

    def test_bid_scores_low(self):
        from spark.memory import score_importance
        score = score_importance("bid_submitted", {})
        assert score <= 0.3

    def test_high_bid_boosts_score(self):
        from spark.memory import score_importance
        low = score_importance("bid_submitted", {"bid_sats": 10})
        high = score_importance("bid_submitted", {"bid_sats": 100})
        assert high > low

    def test_unknown_event_default(self):
        from spark.memory import score_importance
        score = score_importance("unknown_type", {})
        assert score == 0.5


class TestEventRecording:
    def test_record_and_query(self):
        from spark.memory import record_event, get_events
        eid = record_event("task_posted", "Test task", task_id="t1")
        assert eid
        events = get_events(task_id="t1")
        assert len(events) == 1
        assert events[0].event_type == "task_posted"
        assert events[0].description == "Test task"

    def test_record_with_agent(self):
        from spark.memory import record_event, get_events
        record_event("bid_submitted", "Agent bid", agent_id="a1", task_id="t2",
                      data='{"bid_sats": 50}')
        events = get_events(agent_id="a1")
        assert len(events) == 1
        assert events[0].agent_id == "a1"

    def test_filter_by_event_type(self):
        from spark.memory import record_event, get_events
        record_event("task_posted", "posted", task_id="t3")
        record_event("task_completed", "completed", task_id="t3")
        posted = get_events(event_type="task_posted")
        assert len(posted) == 1

    def test_filter_by_min_importance(self):
        from spark.memory import record_event, get_events
        record_event("bid_submitted", "low", importance=0.1)
        record_event("task_failed", "high", importance=0.9)
        high_events = get_events(min_importance=0.5)
        assert len(high_events) == 1
        assert high_events[0].event_type == "task_failed"

    def test_count_events(self):
        from spark.memory import record_event, count_events
        record_event("task_posted", "a")
        record_event("task_posted", "b")
        record_event("task_completed", "c")
        assert count_events() == 3
        assert count_events("task_posted") == 2

    def test_limit_results(self):
        from spark.memory import record_event, get_events
        for i in range(10):
            record_event("bid_submitted", f"bid {i}")
        events = get_events(limit=3)
        assert len(events) == 3


class TestMemoryConsolidation:
    def test_store_and_query_memory(self):
        from spark.memory import store_memory, get_memories
        mid = store_memory("pattern", "agent-x", "Strong performer", confidence=0.8)
        assert mid
        memories = get_memories(subject="agent-x")
        assert len(memories) == 1
        assert memories[0].content == "Strong performer"

    def test_filter_by_type(self):
        from spark.memory import store_memory, get_memories
        store_memory("pattern", "system", "Good pattern")
        store_memory("anomaly", "system", "Bad anomaly")
        patterns = get_memories(memory_type="pattern")
        assert len(patterns) == 1
        assert patterns[0].memory_type == "pattern"

    def test_filter_by_confidence(self):
        from spark.memory import store_memory, get_memories
        store_memory("pattern", "a", "Low conf", confidence=0.2)
        store_memory("pattern", "b", "High conf", confidence=0.9)
        high = get_memories(min_confidence=0.5)
        assert len(high) == 1
        assert high[0].content == "High conf"

    def test_count_memories(self):
        from spark.memory import store_memory, count_memories
        store_memory("pattern", "a", "X")
        store_memory("anomaly", "b", "Y")
        assert count_memories() == 2
        assert count_memories("pattern") == 1


# ── spark.eidos ─────────────────────────────────────────────────────────────


class TestPredictions:
    def test_predict_stores_prediction(self):
        from spark.eidos import predict_task_outcome, get_predictions
        result = predict_task_outcome("t1", "Fix the bug", ["agent-a", "agent-b"])
        assert "prediction_id" in result
        assert result["likely_winner"] == "agent-a"
        preds = get_predictions(task_id="t1")
        assert len(preds) == 1

    def test_predict_with_history(self):
        from spark.eidos import predict_task_outcome
        history = {
            "agent-a": {"success_rate": 0.3, "avg_winning_bid": 40},
            "agent-b": {"success_rate": 0.9, "avg_winning_bid": 30},
        }
        result = predict_task_outcome(
            "t2", "Research topic", ["agent-a", "agent-b"],
            agent_history=history,
        )
        assert result["likely_winner"] == "agent-b"
        assert result["success_probability"] > 0.5

    def test_predict_empty_candidates(self):
        from spark.eidos import predict_task_outcome
        result = predict_task_outcome("t3", "No agents", [])
        assert result["likely_winner"] is None


class TestEvaluation:
    def test_evaluate_correct_prediction(self):
        from spark.eidos import predict_task_outcome, evaluate_prediction
        predict_task_outcome("t4", "Task", ["agent-a"])
        result = evaluate_prediction("t4", "agent-a", task_succeeded=True, winning_bid=30)
        assert result is not None
        assert result["accuracy"] > 0.0

    def test_evaluate_wrong_prediction(self):
        from spark.eidos import predict_task_outcome, evaluate_prediction
        predict_task_outcome("t5", "Task", ["agent-a"])
        result = evaluate_prediction("t5", "agent-b", task_succeeded=False)
        assert result is not None
        # Wrong winner + failed = lower accuracy
        assert result["accuracy"] < 1.0

    def test_evaluate_no_prediction_returns_none(self):
        from spark.eidos import evaluate_prediction
        result = evaluate_prediction("no-task", "agent-a", task_succeeded=True)
        assert result is None

    def test_double_evaluation_returns_none(self):
        from spark.eidos import predict_task_outcome, evaluate_prediction
        predict_task_outcome("t6", "Task", ["agent-a"])
        evaluate_prediction("t6", "agent-a", task_succeeded=True)
        # Second evaluation should return None (already evaluated)
        result = evaluate_prediction("t6", "agent-a", task_succeeded=True)
        assert result is None


class TestAccuracyStats:
    def test_empty_stats(self):
        from spark.eidos import get_accuracy_stats
        stats = get_accuracy_stats()
        assert stats["total_predictions"] == 0
        assert stats["evaluated"] == 0
        assert stats["avg_accuracy"] == 0.0

    def test_stats_after_evaluations(self):
        from spark.eidos import predict_task_outcome, evaluate_prediction, get_accuracy_stats
        for i in range(3):
            predict_task_outcome(f"task-{i}", "Description", ["agent-a"])
            evaluate_prediction(f"task-{i}", "agent-a", task_succeeded=True, winning_bid=30)
        stats = get_accuracy_stats()
        assert stats["total_predictions"] == 3
        assert stats["evaluated"] == 3
        assert stats["pending"] == 0
        assert stats["avg_accuracy"] > 0.0


class TestComputeAccuracy:
    def test_perfect_prediction(self):
        from spark.eidos import _compute_accuracy
        predicted = {
            "likely_winner": "agent-a",
            "success_probability": 1.0,
            "estimated_bid_range": [20, 40],
        }
        actual = {"winner": "agent-a", "succeeded": True, "winning_bid": 30}
        acc = _compute_accuracy(predicted, actual)
        assert acc == pytest.approx(1.0, abs=0.01)

    def test_all_wrong(self):
        from spark.eidos import _compute_accuracy
        predicted = {
            "likely_winner": "agent-a",
            "success_probability": 1.0,
            "estimated_bid_range": [10, 20],
        }
        actual = {"winner": "agent-b", "succeeded": False, "winning_bid": 100}
        acc = _compute_accuracy(predicted, actual)
        assert acc < 0.5

    def test_partial_credit(self):
        from spark.eidos import _compute_accuracy
        predicted = {
            "likely_winner": "agent-a",
            "success_probability": 0.5,
            "estimated_bid_range": [20, 40],
        }
        actual = {"winner": "agent-b", "succeeded": True, "winning_bid": 30}
        acc = _compute_accuracy(predicted, actual)
        # Wrong winner but right success and in bid range → partial
        assert 0.2 < acc < 0.8


# ── spark.advisor ───────────────────────────────────────────────────────────


class TestAdvisor:
    def test_insufficient_data(self):
        from spark.advisor import generate_advisories
        advisories = generate_advisories()
        assert len(advisories) >= 1
        assert advisories[0].category == "system_health"
        assert "Insufficient" in advisories[0].title

    def test_failure_detection(self):
        from spark.memory import record_event
        from spark.advisor import generate_advisories
        # Record enough events to pass the minimum threshold
        for i in range(5):
            record_event("task_failed", f"Failed task {i}",
                         agent_id="agent-bad", task_id=f"t-{i}")
        advisories = generate_advisories()
        failure_advisories = [a for a in advisories if a.category == "failure_prevention"]
        assert len(failure_advisories) >= 1
        assert "agent-ba" in failure_advisories[0].title

    def test_advisories_sorted_by_priority(self):
        from spark.memory import record_event
        from spark.advisor import generate_advisories
        for i in range(4):
            record_event("task_posted", f"posted {i}", task_id=f"p-{i}")
            record_event("task_completed", f"done {i}",
                         agent_id="agent-good", task_id=f"p-{i}")
        advisories = generate_advisories()
        if len(advisories) >= 2:
            assert advisories[0].priority >= advisories[-1].priority

    def test_no_activity_advisory(self):
        from spark.advisor import _check_system_activity
        advisories = _check_system_activity()
        assert len(advisories) >= 1
        assert "No swarm activity" in advisories[0].title


# ── spark.engine ────────────────────────────────────────────────────────────


class TestSparkEngine:
    def test_engine_enabled(self):
        from spark.engine import SparkEngine
        engine = SparkEngine(enabled=True)
        assert engine.enabled

    def test_engine_disabled(self):
        from spark.engine import SparkEngine
        engine = SparkEngine(enabled=False)
        result = engine.on_task_posted("t1", "Ignored task")
        assert result is None

    def test_on_task_posted(self):
        from spark.engine import SparkEngine
        from spark.memory import get_events
        engine = SparkEngine(enabled=True)
        eid = engine.on_task_posted("t1", "Test task", ["agent-a"])
        assert eid is not None
        events = get_events(task_id="t1")
        assert len(events) == 1

    def test_on_bid_submitted(self):
        from spark.engine import SparkEngine
        from spark.memory import get_events
        engine = SparkEngine(enabled=True)
        eid = engine.on_bid_submitted("t1", "agent-a", 50)
        assert eid is not None
        events = get_events(event_type="bid_submitted")
        assert len(events) == 1

    def test_on_task_assigned(self):
        from spark.engine import SparkEngine
        from spark.memory import get_events
        engine = SparkEngine(enabled=True)
        eid = engine.on_task_assigned("t1", "agent-a")
        assert eid is not None
        events = get_events(event_type="task_assigned")
        assert len(events) == 1

    def test_on_task_completed_evaluates_prediction(self):
        from spark.engine import SparkEngine
        from spark.eidos import get_predictions
        engine = SparkEngine(enabled=True)
        engine.on_task_posted("t1", "Fix bug", ["agent-a"])
        eid = engine.on_task_completed("t1", "agent-a", "Fixed it")
        assert eid is not None
        preds = get_predictions(task_id="t1")
        # Should have prediction(s) evaluated
        assert len(preds) >= 1

    def test_on_task_failed(self):
        from spark.engine import SparkEngine
        from spark.memory import get_events
        engine = SparkEngine(enabled=True)
        engine.on_task_posted("t1", "Deploy server", ["agent-a"])
        eid = engine.on_task_failed("t1", "agent-a", "Connection timeout")
        assert eid is not None
        events = get_events(event_type="task_failed")
        assert len(events) == 1

    def test_on_agent_joined(self):
        from spark.engine import SparkEngine
        from spark.memory import get_events
        engine = SparkEngine(enabled=True)
        eid = engine.on_agent_joined("agent-a", "Echo")
        assert eid is not None
        events = get_events(event_type="agent_joined")
        assert len(events) == 1

    def test_status(self):
        from spark.engine import SparkEngine
        engine = SparkEngine(enabled=True)
        engine.on_task_posted("t1", "Test", ["agent-a"])
        engine.on_bid_submitted("t1", "agent-a", 30)
        status = engine.status()
        assert status["enabled"] is True
        assert status["events_captured"] >= 2
        assert "predictions" in status
        assert "event_types" in status

    def test_get_advisories(self):
        from spark.engine import SparkEngine
        engine = SparkEngine(enabled=True)
        advisories = engine.get_advisories()
        assert isinstance(advisories, list)

    def test_get_advisories_disabled(self):
        from spark.engine import SparkEngine
        engine = SparkEngine(enabled=False)
        advisories = engine.get_advisories()
        assert advisories == []

    def test_get_timeline(self):
        from spark.engine import SparkEngine
        engine = SparkEngine(enabled=True)
        engine.on_task_posted("t1", "Task 1")
        engine.on_task_posted("t2", "Task 2")
        timeline = engine.get_timeline(limit=10)
        assert len(timeline) == 2

    def test_memory_consolidation(self):
        from spark.engine import SparkEngine
        from spark.memory import get_memories
        engine = SparkEngine(enabled=True)
        # Generate enough completions to trigger consolidation (>=5 events, >=3 outcomes)
        for i in range(6):
            engine.on_task_completed(f"t-{i}", "agent-star", f"Result {i}")
        memories = get_memories(subject="agent-star")
        # Should have at least one consolidated memory about strong performance
        assert len(memories) >= 1


# ── Dashboard routes ────────────────────────────────────────────────────────


class TestSparkRoutes:
    def test_spark_json(self, client):
        resp = client.get("/spark")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "advisories" in data

    def test_spark_ui(self, client):
        resp = client.get("/spark/ui")
        assert resp.status_code == 200
        assert "SPARK INTELLIGENCE" in resp.text

    def test_spark_timeline(self, client):
        resp = client.get("/spark/timeline")
        assert resp.status_code == 200

    def test_spark_insights(self, client):
        resp = client.get("/spark/insights")
        assert resp.status_code == 200
