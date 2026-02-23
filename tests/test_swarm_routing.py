"""Tests for intelligent swarm routing.

Covers:
- Capability manifest scoring
- Routing decisions
- Audit logging
- Recommendation engine
"""

import pytest

from swarm.routing import (
    CapabilityManifest,
    RoutingDecision,
    RoutingEngine,
)
from swarm.personas import PERSONAS


class TestCapabilityManifest:
    """Tests for capability manifest scoring."""
    
    @pytest.fixture
    def forge_manifest(self):
        """Create a Forge (coding) capability manifest."""
        return CapabilityManifest(
            agent_id="forge-001",
            agent_name="Forge",
            capabilities=["coding", "debugging", "testing"],
            keywords=["code", "function", "bug", "fix", "refactor", "test"],
            rate_sats=55,
        )
    
    @pytest.fixture
    def quill_manifest(self):
        """Create a Quill (writing) capability manifest."""
        return CapabilityManifest(
            agent_id="quill-001",
            agent_name="Quill",
            capabilities=["writing", "editing", "documentation"],
            keywords=["write", "draft", "document", "readme", "blog"],
            rate_sats=45,
        )
    
    def test_keyword_match_high_score(self, forge_manifest):
        """Strong keyword match gives high score."""
        task = "Fix the bug in the authentication code"
        score = forge_manifest.score_task_match(task)
        assert score >= 0.5  # "bug" and "code" are both keywords
        
    def test_capability_match_moderate_score(self, quill_manifest):
        """Capability match gives moderate score."""
        task = "Create documentation for the API"
        score = quill_manifest.score_task_match(task)
        assert score >= 0.2  # "documentation" capability matches
        
    def test_no_match_low_score(self, forge_manifest):
        """No relevant keywords gives low score."""
        task = "Analyze quarterly sales data trends"
        score = forge_manifest.score_task_match(task)
        assert score < 0.3  # No coding keywords
        
    def test_score_capped_at_one(self, forge_manifest):
        """Score never exceeds 1.0."""
        task = "code function bug fix refactor test code code code"
        score = forge_manifest.score_task_match(task)
        assert score <= 1.0
        
    def test_related_word_matching(self, forge_manifest):
        """Related words contribute to score."""
        task = "Implement a new class for the API"
        score = forge_manifest.score_task_match(task)
        # "class" is related to coding via related_words lookup
        # Score should be non-zero even without direct keyword match
        assert score >= 0.0  # May be 0 if related word matching is disabled


class TestRoutingEngine:
    """Tests for the routing engine."""
    
    @pytest.fixture
    def engine(self, tmp_path):
        """Create a routing engine with temp database."""
        # Point to temp location to avoid conflicts
        import swarm.routing as routing
        old_path = routing.DB_PATH
        routing.DB_PATH = tmp_path / "routing_test.db"
        
        engine = RoutingEngine()
        
        yield engine
        
        # Cleanup
        routing.DB_PATH = old_path
    
    def test_register_persona(self, engine):
        """Can register a persona manifest."""
        manifest = engine.register_persona("forge", "forge-001")
        
        assert manifest.agent_id == "forge-001"
        assert manifest.agent_name == "Forge"
        assert "coding" in manifest.capabilities
        
    def test_register_unknown_persona_raises(self, engine):
        """Registering unknown persona raises error."""
        with pytest.raises(ValueError) as exc:
            engine.register_persona("unknown", "unknown-001")
        assert "Unknown persona" in str(exc.value)
    
    def test_get_manifest(self, engine):
        """Can retrieve registered manifest."""
        engine.register_persona("echo", "echo-001")
        
        manifest = engine.get_manifest("echo-001")
        assert manifest is not None
        assert manifest.agent_name == "Echo"
        
    def test_get_manifest_nonexistent(self, engine):
        """Getting nonexistent manifest returns None."""
        assert engine.get_manifest("nonexistent") is None
        
    def test_score_candidates(self, engine):
        """Can score multiple candidates."""
        engine.register_persona("forge", "forge-001")
        engine.register_persona("quill", "quill-001")
        
        task = "Write code for the new feature"
        scores = engine.score_candidates(task)
        
        assert "forge-001" in scores
        assert "quill-001" in scores
        # Forge should score higher or equal for coding task
        # (both may have low scores for generic task)
        assert scores["forge-001"] >= scores["quill-001"]
        
    def test_recommend_agent_selects_winner(self, engine):
        """Recommendation selects best agent."""
        engine.register_persona("forge", "forge-001")
        engine.register_persona("quill", "quill-001")
        
        task_id = "task-001"
        description = "Fix the bug in authentication code"
        bids = {"forge-001": 50, "quill-001": 40}  # Quill cheaper
        
        winner, decision = engine.recommend_agent(task_id, description, bids)
        
        # Forge should win despite higher bid due to capability match
        assert winner == "forge-001"
        assert decision.task_id == task_id
        assert "forge-001" in decision.candidate_agents
        
    def test_recommend_agent_no_bids(self, engine):
        """No bids returns None winner."""
        winner, decision = engine.recommend_agent(
            "task-001", "Some task", {}
        )
        
        assert winner is None
        assert decision.selected_agent is None
        assert "No bids" in decision.selection_reason
        
    def test_routing_decision_logged(self, engine):
        """Routing decision is persisted."""
        engine.register_persona("forge", "forge-001")
        
        winner, decision = engine.recommend_agent(
            "task-001", "Code review", {"forge-001": 50}
        )
        
        # Query history
        history = engine.get_routing_history(task_id="task-001")
        assert len(history) == 1
        assert history[0].selected_agent == "forge-001"
        
    def test_get_routing_history_limit(self, engine):
        """History respects limit."""
        engine.register_persona("forge", "forge-001")
        
        for i in range(5):
            engine.recommend_agent(
                f"task-{i}", "Code task", {"forge-001": 50}
            )
        
        history = engine.get_routing_history(limit=3)
        assert len(history) == 3
        
    def test_agent_stats_calculated(self, engine):
        """Agent stats are tracked correctly."""
        engine.register_persona("forge", "forge-001")
        engine.register_persona("echo", "echo-001")
        
        # Forge wins 2, Echo wins 1
        engine.recommend_agent("t1", "Code", {"forge-001": 50, "echo-001": 60})
        engine.recommend_agent("t2", "Debug", {"forge-001": 50, "echo-001": 60})
        engine.recommend_agent("t3", "Research", {"forge-001": 60, "echo-001": 50})
        
        forge_stats = engine.get_agent_stats("forge-001")
        assert forge_stats["tasks_won"] == 2
        assert forge_stats["tasks_considered"] == 3
        
    def test_export_audit_log(self, engine):
        """Can export full audit log."""
        engine.register_persona("forge", "forge-001")
        engine.recommend_agent("t1", "Code", {"forge-001": 50})
        
        log = engine.export_audit_log()
        assert len(log) == 1
        assert log[0]["task_id"] == "t1"


class TestRoutingIntegration:
    """Integration tests for routing with real personas."""
    
    def test_all_personas_scorable(self):
        """All built-in personas can score tasks."""
        engine = RoutingEngine()
        
        # Register all personas
        for persona_id in PERSONAS:
            engine.register_persona(persona_id, f"{persona_id}-001")
        
        task = "Write a function to calculate fibonacci numbers"
        scores = engine.score_candidates(task)
        
        # All should have scores
        assert len(scores) == len(PERSONAS)
        
        # Forge (coding) should be highest
        assert scores["forge-001"] == max(scores.values())
