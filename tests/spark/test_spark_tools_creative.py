"""Tests for Spark engine tool-level and creative pipeline event capture.

Covers the new on_tool_executed() and on_creative_step() methods added
in Phase 6.
"""

import pytest

from spark.engine import SparkEngine
from spark.memory import get_events, count_events


@pytest.fixture(autouse=True)
def tmp_spark_db(tmp_path, monkeypatch):
    db_path = tmp_path / "spark.db"
    monkeypatch.setattr("spark.memory.DB_PATH", db_path)
    monkeypatch.setattr("spark.eidos.DB_PATH", db_path)
    yield db_path


class TestOnToolExecuted:
    def test_captures_tool_event(self):
        engine = SparkEngine(enabled=True)
        eid = engine.on_tool_executed("agent-a", "git_commit", task_id="t1")
        assert eid is not None
        events = get_events(event_type="tool_executed")
        assert len(events) == 1
        assert "git_commit" in events[0].description

    def test_captures_tool_failure(self):
        engine = SparkEngine(enabled=True)
        eid = engine.on_tool_executed("agent-a", "generate_image", success=False)
        assert eid is not None
        events = get_events(event_type="tool_executed")
        assert len(events) == 1
        assert "FAIL" in events[0].description

    def test_captures_duration(self):
        engine = SparkEngine(enabled=True)
        engine.on_tool_executed("agent-a", "generate_song", duration_ms=5000)
        events = get_events(event_type="tool_executed")
        assert len(events) == 1

    def test_disabled_returns_none(self):
        engine = SparkEngine(enabled=False)
        result = engine.on_tool_executed("agent-a", "git_push")
        assert result is None

    def test_multiple_tool_events(self):
        engine = SparkEngine(enabled=True)
        engine.on_tool_executed("agent-a", "git_add")
        engine.on_tool_executed("agent-a", "git_commit")
        engine.on_tool_executed("agent-a", "git_push")
        assert count_events("tool_executed") == 3


class TestOnCreativeStep:
    def test_captures_creative_step(self):
        engine = SparkEngine(enabled=True)
        eid = engine.on_creative_step(
            project_id="proj-1",
            step_name="storyboard",
            agent_id="pixel-001",
            output_path="/data/images/frame.png",
        )
        assert eid is not None
        events = get_events(event_type="creative_step")
        assert len(events) == 1
        assert "storyboard" in events[0].description

    def test_captures_failed_step(self):
        engine = SparkEngine(enabled=True)
        engine.on_creative_step(
            project_id="proj-1",
            step_name="music",
            agent_id="lyra-001",
            success=False,
        )
        events = get_events(event_type="creative_step")
        assert len(events) == 1
        assert "FAIL" in events[0].description

    def test_disabled_returns_none(self):
        engine = SparkEngine(enabled=False)
        result = engine.on_creative_step("p1", "storyboard", "pixel-001")
        assert result is None

    def test_full_pipeline_events(self):
        engine = SparkEngine(enabled=True)
        steps = ["storyboard", "music", "video", "assembly"]
        agents = ["pixel-001", "lyra-001", "reel-001", "reel-001"]
        for step, agent in zip(steps, agents):
            engine.on_creative_step("proj-1", step, agent)
        assert count_events("creative_step") == 4


class TestSparkStatusIncludesNewTypes:
    def test_status_includes_tool_executed(self):
        engine = SparkEngine(enabled=True)
        engine.on_tool_executed("a", "git_commit")
        status = engine.status()
        assert "tool_executed" in status["event_types"]
        assert status["event_types"]["tool_executed"] == 1

    def test_status_includes_creative_step(self):
        engine = SparkEngine(enabled=True)
        engine.on_creative_step("p1", "storyboard", "pixel-001")
        status = engine.status()
        assert "creative_step" in status["event_types"]
        assert status["event_types"]["creative_step"] == 1
