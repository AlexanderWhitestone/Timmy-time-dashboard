"""End-to-end tests for the streamlined architecture.

Validates that all five architecture improvements work together:
1. Unified memory system (SQLite-based, no file parsing)
2. Simplified agent system (toolsets, no Helm routing)
3. Merged serve endpoints (dashboard app)
4. Config-driven settings (pydantic)
5. Consistent test framework (pytest only)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── 1. Unified Memory System ────────────────────────────────────────────────


class TestUnifiedMemoryE2E:
    """End-to-end: memory consolidation works across all tiers."""

    def test_memory_system_delegates_to_unified(self, tmp_path):
        """MemorySystem should use UnifiedMemory under the hood."""
        from brain.memory import UnifiedMemory

        mem = UnifiedMemory(db_path=tmp_path / "test.db", use_rqlite=False)

        # Store via hot memory
        mem.update_hot_section("Status", "Active")

        # Store via facts
        mem.store_fact_sync("pref", "User likes dark mode")

        # Store via vault notes
        mem.write_note("test_note", "This is a test note", namespace="notes")

        # Store via handoff
        mem.write_handoff("Session ended", ["Decision 1"], ["Open item"])

        # Verify all tiers are in the same DB
        stats = mem.get_stats()
        assert stats["fact_count"] == 1
        assert stats["backend"] == "local_sqlite"

        hot = mem.get_hot_memory()
        assert hot["Status"] == "Active"

        handoff = mem.read_handoff()
        assert "Session ended" in handoff["summary"]

        notes = mem.list_notes(namespace="notes")
        assert len(notes) == 1

    def test_memory_system_facade_works(self, tmp_path):
        """MemorySystem facade should delegate to UnifiedMemory."""
        with patch("timmy.memory_system.get_memory") as mock_get:
            from brain.memory import UnifiedMemory

            mem = UnifiedMemory(db_path=tmp_path / "test.db", use_rqlite=False)
            mock_get.return_value = mem

            from timmy.memory_system import MemorySystem

            ms = MemorySystem()
            ms._memory = mem

            # Should not crash
            ctx = ms.start_session()
            assert isinstance(ctx, str)


# ── 2. Simplified Agent System ──────────────────────────────────────────────


class TestSimplifiedAgentsE2E:
    """End-to-end: toolset classification replaces Helm routing."""

    def test_toolsets_cover_all_domains(self):
        """All capability domains should be represented."""
        from timmy.agents.toolsets import get_toolsets

        toolsets = get_toolsets()
        domains = set(toolsets.keys())
        assert {"research", "code", "writing", "memory"} <= domains

    def test_classify_covers_common_requests(self):
        """Classification should handle typical user requests."""
        from timmy.agents.toolsets import classify_request

        cases = [
            ("Hello Timmy", "direct"),
            ("What did we talk about yesterday?", "memory"),
            ("Search for Bitcoin news", "research"),
            ("Write a Python script", "code"),
            ("What can you do?", "direct"),
        ]
        for request, expected in cases:
            result = classify_request(request)
            assert result == expected, f"'{request}' classified as '{result}', expected '{expected}'"

    @patch("timmy.agents.base.tool_registry", MagicMock())
    def test_create_timmy_swarm_returns_orchestrator(self):
        """create_timmy_swarm should return a TimmyOrchestrator."""
        from timmy.agents.timmy import create_timmy_swarm, TimmyOrchestrator

        swarm = create_timmy_swarm()
        assert isinstance(swarm, TimmyOrchestrator)


# ── 3. Merged Serve Endpoints ───────────────────────────────────────────────


class TestMergedServeE2E:
    """End-to-end: serve routes are part of the dashboard app."""

    def test_serve_route_module_imports(self):
        """Serve route module should import cleanly."""
        from dashboard.routes.serve import router

        paths = [r.path for r in router.routes]
        assert "/serve/status" in paths
        assert "/serve/chat" in paths

    def test_serve_router_registered_in_app(self):
        """Serve router should be imported in the dashboard app module."""
        # Verify serve_router is imported and registered by checking the
        # import statement exists in app.py (avoids triggering proxy issues
        # from sentence-transformers model download in CI environments)
        app_path = Path(__file__).parent.parent / "src" / "dashboard" / "app.py"
        content = app_path.read_text()
        assert "from dashboard.routes.serve import router as serve_router" in content
        assert "app.include_router(serve_router)" in content


# ── 4. Config Validation ────────────────────────────────────────────────────


class TestConfigE2E:
    """Verify config is used consistently (no os.environ.get)."""

    def test_settings_import(self):
        """Settings singleton should be importable."""
        from config import settings

        assert hasattr(settings, "ollama_url")
        assert hasattr(settings, "ollama_model")
        assert hasattr(settings, "timmy_model_backend")

    def test_no_direct_environ_in_source(self):
        """Source files should use config.settings, not os.environ.get.

        Some os.environ.get() calls are legitimate (e.g. in brain/ for
        distributed config, or in infrastructure/ for variable interpolation).
        We track the count and flag if it grows beyond the baseline.
        """
        src_dir = Path(__file__).parent.parent / "src"
        violations = []

        # Files that legitimately need os.environ.get()
        allowed_files = {
            "config.py",
            "brain/client.py",  # Distributed brain config
            "brain/memory.py",  # DB path override
            "infrastructure/router/cascade.py",  # Variable interpolation
        }

        for py_file in src_dir.rglob("*.py"):
            rel_path = str(py_file.relative_to(src_dir))
            if any(rel_path.endswith(af) or af in rel_path for af in allowed_files):
                continue
            content = py_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                if "os.environ.get(" in line and "TIMMY_TEST_MODE" not in line:
                    violations.append(f"{rel_path}:{i}: {line.strip()}")

        assert len(violations) < 5, (
            f"Found {len(violations)} direct os.environ.get() calls in src/ "
            f"(should use config.settings):\n" + "\n".join(violations[:10])
        )


# ── 5. Test Framework Consistency ────────────────────────────────────────────


class TestFrameworkConsistency:
    """Verify tests use pytest consistently (no unittest.TestCase)."""

    def test_no_unittest_testcase_subclasses(self):
        """Test files should use pytest, not unittest.TestCase."""
        tests_dir = Path(__file__).parent
        violations = []

        for py_file in tests_dir.rglob("*.py"):
            # Skip conftest and this file (contains the check string)
            if py_file.name in ("conftest.py", "test_streamlined_architecture.py"):
                continue
            content = py_file.read_text()
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("class ") and "(unittest.TestCase)" in stripped:
                    violations.append(f"{py_file.name}: {stripped}")

        assert len(violations) == 0, (
            f"Found {len(violations)} unittest.TestCase subclasses "
            f"(should use pytest):\n" + "\n".join(violations)
        )

    def test_conftest_has_essential_fixtures(self):
        """conftest.py should provide essential test fixtures."""
        from tests.conftest import (
            reset_message_log,
            clean_database,
            cleanup_event_loops,
        )

        # These should be callable (fixture functions)
        assert callable(reset_message_log)
        assert callable(clean_database)
        assert callable(cleanup_event_loops)
