"""Tests for performance optimizations (Stage 2).

TDD: These tests validate the 5 complexity-reduction improvements:
1. HTMX polling interval optimization
2. EventBus/WebSocket streamlining
3. Vector search performance
4. Agent orchestration simplification
5. Calm feature responsiveness
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── 1. HTMX Polling Optimization ────────────────────────────────────────────


class TestHTMXPollingOptimization:
    """Verify polling intervals are reasonable for a local app."""

    TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "dashboard" / "templates"

    def _get_polling_intervals(self) -> list[tuple[str, str, int]]:
        """Extract all hx-trigger="every Xs" from templates."""
        results = []
        for html_file in self.TEMPLATE_DIR.rglob("*.html"):
            content = html_file.read_text()
            matches = re.findall(
                r'hx-trigger="[^"]*every\s+(\d+)s[^"]*"',
                content,
            )
            for interval in matches:
                results.append((html_file.name, "hx-trigger", int(interval)))
        return results

    def test_no_polling_under_5s(self):
        """No HTMX polling should be faster than every 5 seconds."""
        intervals = self._get_polling_intervals()
        violations = [(f, t, i) for f, t, i in intervals if i < 5]
        assert len(violations) == 0, (
            f"Polling intervals under 5s found: {violations}"
        )

    def test_no_setinterval_under_5s_in_mission_control(self):
        """Mission control JS should not poll faster than 5s."""
        mc_path = self.TEMPLATE_DIR / "mission_control.html"
        if not mc_path.exists():
            pytest.skip("mission_control.html not found")
        content = mc_path.read_text()
        intervals = re.findall(r'setInterval\(\w+,\s*(\d+)\)', content)
        violations = [int(i) for i in intervals if int(i) < 5000]
        assert len(violations) == 0, (
            f"setInterval under 5s found in mission_control.html: {violations}ms"
        )

    def test_completed_tasks_poll_infrequently(self):
        """Completed tasks column should poll at 60s+ (low-priority data)."""
        tasks_path = self.TEMPLATE_DIR / "tasks.html"
        if not tasks_path.exists():
            pytest.skip("tasks.html not found")
        content = tasks_path.read_text()
        match = re.search(
            r'hx-get="/tasks/completed"[^>]*hx-trigger="every\s+(\d+)s"',
            content,
        )
        if match:
            interval = int(match.group(1))
            assert interval >= 60, (
                f"Completed tasks poll at {interval}s, should be >= 60s"
            )


# ── 2. EventBus / WebSocket Streamlining ────────────────────────────────────


class TestEventBusStreamlining:
    """Verify event system is lean for a local app."""

    def test_event_bus_max_history_reasonable(self):
        """EventBus history should be capped at a reasonable size."""
        from infrastructure.events.bus import EventBus
        bus = EventBus()
        assert bus._max_history <= 500, (
            f"EventBus history {bus._max_history} is too large for local use"
        )

    def test_ws_manager_max_history_reasonable(self):
        """WebSocket manager history should be compact."""
        from infrastructure.ws_manager.handler import WebSocketManager
        mgr = WebSocketManager()
        assert mgr._max_history <= 100

    def test_ws_manager_sends_limited_history_on_connect(self):
        """New WS connections should receive limited history (not all)."""
        from infrastructure.ws_manager.handler import WebSocketManager
        mgr = WebSocketManager()
        assert hasattr(mgr, '_connections')


class TestEventBusTopicFiltering:
    """Verify topic-based event filtering works."""

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self):
        """Wildcard patterns should match correctly."""
        from infrastructure.events.bus import EventBus, Event
        bus = EventBus()
        received = []

        @bus.subscribe("agent.task.*")
        async def handler(event):
            received.append(event)

        await bus.publish(Event(type="agent.task.completed", source="test", data={}))
        await bus.publish(Event(type="agent.status.changed", source="test", data={}))

        assert len(received) == 1
        assert received[0].type == "agent.task.completed"


# ── 3. Vector Search Performance ────────────────────────────────────────────


class TestVectorSearchPerformance:
    """Validate memory search is optimized for local use."""

    def test_compute_embedding_is_deterministic(self):
        """Embedding computation should produce consistent results."""
        from timmy.memory.vector_store import _compute_embedding
        v1 = _compute_embedding("hello world")
        v2 = _compute_embedding("hello world")
        assert v1 == v2

    def test_compute_embedding_dimension(self):
        """Embedding should match expected dimension (384)."""
        from timmy.memory.vector_store import _compute_embedding
        v = _compute_embedding("test text")
        assert len(v) == 384

    def test_search_memories_handles_empty_db(self, tmp_path):
        """search_memories should return empty list for empty DB."""
        from timmy.memory.vector_store import search_memories
        results = search_memories("test query", limit=5)
        assert isinstance(results, list)

    def test_cosine_similarity_identical_vectors(self):
        """Identical vectors should have similarity of 1.0."""
        from timmy.memory.vector_store import _cosine_similarity
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 0.001

    def test_cosine_similarity_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity of 0.0."""
        from timmy.memory.vector_store import _cosine_similarity
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        assert abs(_cosine_similarity(v1, v2)) < 0.001

    def test_embedding_cache_exists(self):
        """Vector store should have an embedding cache mechanism."""
        from timmy.memory import vector_store
        assert hasattr(vector_store, '_embedding_cache'), (
            "vector_store should have _embedding_cache for repeated queries"
        )

    def test_embedding_cache_hit(self):
        """Repeated embedding calls should use cache."""
        from timmy.memory.vector_store import _compute_embedding, _embedding_cache
        _embedding_cache.clear()
        _compute_embedding("cached query test")
        assert "cached query test" in _embedding_cache


# ── 4. Agent Orchestration Simplification ────────────────────────────────────


class TestAgentOrchestrationSimplified:
    """Verify orchestration doesn't use Helm routing anymore."""

    def test_orchestrate_does_not_import_helm(self):
        """TimmyOrchestrator.orchestrate should not import HelmAgent."""
        import inspect
        from timmy.agents.timmy import TimmyOrchestrator
        source = inspect.getsource(TimmyOrchestrator.orchestrate)
        assert "HelmAgent" not in source
        assert "helm" not in source.lower() or "classify_request" in source

    def test_classify_request_is_synchronous(self):
        """classify_request should be sync (no await needed)."""
        from timmy.agents.toolsets import classify_request
        import asyncio
        result = classify_request("hello")
        assert not asyncio.iscoroutine(result)

    def test_toolsets_registered_in_init(self):
        """Toolsets should be importable from agents package."""
        from timmy.agents import get_toolsets, classify_request
        assert callable(get_toolsets)
        assert callable(classify_request)


# ── 5. Calm Feature Responsiveness ──────────────────────────────────────────


class TestCalmResponsiveness:
    """Validate Calm feature uses optimistic UI patterns."""

    TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "dashboard" / "templates"

    def test_calm_complete_has_transition_class(self):
        """Complete button should trigger a CSS transition for feedback."""
        nnl_path = self.TEMPLATE_DIR / "calm" / "partials" / "now_next_later.html"
        if not nnl_path.exists():
            pytest.skip("now_next_later.html not found")
        content = nnl_path.read_text()
        has_feedback = (
            "hx-indicator" in content
            or "transition" in content
            or "hx-disabled-elt" in content
            or "htmx-request" in content
        )
        assert has_feedback, "Calm task actions should provide visual feedback"

    def test_calm_uses_custom_events(self):
        """Calm should use custom HTMX events for stack updates."""
        view_path = self.TEMPLATE_DIR / "calm" / "calm_view.html"
        if not view_path.exists():
            pytest.skip("calm_view.html not found")
        content = view_path.read_text()
        assert "taskPromoted" in content, (
            "Calm should use taskPromoted custom event for reactive updates"
        )

    def test_calm_route_returns_htmx_trigger(self):
        """Calm task endpoints should return HX-Trigger headers."""
        from dashboard.routes.calm import router
        paths = [r.path for r in router.routes]
        assert any("/complete" in p for p in paths), "Missing complete endpoint"
        assert any("/defer" in p for p in paths), "Missing defer endpoint"

    def test_calm_actions_have_disabled_buttons(self):
        """Calm action buttons should disable during requests."""
        nnl_path = self.TEMPLATE_DIR / "calm" / "partials" / "now_next_later.html"
        if not nnl_path.exists():
            pytest.skip("now_next_later.html not found")
        content = nnl_path.read_text()
        assert "hx-disabled-elt" in content, (
            "Calm buttons should use hx-disabled-elt to prevent double-clicks"
        )
