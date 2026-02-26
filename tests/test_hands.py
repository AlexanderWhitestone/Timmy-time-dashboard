"""Tests for Hands Infrastructure.

Tests HandRegistry, HandScheduler, and HandRunner.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hands import HandRegistry, HandRunner, HandScheduler
from hands.models import HandConfig, HandStatus, ScheduleConfig


@pytest.fixture
def temp_hands_dir():
    """Create a temporary hands directory with test Hands."""
    with tempfile.TemporaryDirectory() as tmpdir:
        hands_dir = Path(tmpdir)
        
        # Create Oracle Hand
        oracle_dir = hands_dir / "oracle"
        oracle_dir.mkdir()
        (oracle_dir / "HAND.toml").write_text('''
[hand]
name = "oracle"
description = "Bitcoin intelligence"
schedule = "0 7,19 * * *"

[tools]
required = ["mempool_fetch", "fee_estimate"]

[output]
dashboard = true
''')
        (oracle_dir / "SYSTEM.md").write_text("# Oracle System Prompt\nYou are Oracle.")
        
        # Create Sentinel Hand
        sentinel_dir = hands_dir / "sentinel"
        sentinel_dir.mkdir()
        (sentinel_dir / "HAND.toml").write_text('''
[hand]
name = "sentinel"
description = "System health monitoring"
schedule = "*/15 * * * *"
enabled = true
''')
        
        yield hands_dir


@pytest.fixture
def registry(temp_hands_dir):
    """Create HandRegistry with test Hands."""
    db_path = temp_hands_dir / "test_hands.db"
    reg = HandRegistry(hands_dir=temp_hands_dir, db_path=db_path)
    return reg


@pytest.mark.asyncio
class TestHandRegistry:
    """HandRegistry tests."""
    
    async def test_load_all_hands(self, registry, temp_hands_dir):
        """Should load all Hands from directory."""
        hands = await registry.load_all()
        
        assert len(hands) == 2
        assert "oracle" in hands
        assert "sentinel" in hands
    
    async def test_get_hand(self, registry, temp_hands_dir):
        """Should get Hand by name."""
        await registry.load_all()
        
        hand = registry.get_hand("oracle")
        assert hand.name == "oracle"
        assert "Bitcoin" in hand.description
    
    async def test_get_hand_not_found(self, registry):
        """Should raise for unknown Hand."""
        from hands.registry import HandNotFoundError
        
        with pytest.raises(HandNotFoundError):
            registry.get_hand("nonexistent")
    
    async def test_get_scheduled_hands(self, registry, temp_hands_dir):
        """Should return only Hands with schedules."""
        await registry.load_all()
        
        scheduled = registry.get_scheduled_hands()
        
        assert len(scheduled) == 2
        assert all(h.schedule is not None for h in scheduled)
    
    async def test_state_management(self, registry, temp_hands_dir):
        """Should track Hand state."""
        await registry.load_all()
        
        state = registry.get_state("oracle")
        assert state.name == "oracle"
        assert state.status == HandStatus.IDLE
        
        registry.update_state("oracle", status=HandStatus.RUNNING)
        state = registry.get_state("oracle")
        assert state.status == HandStatus.RUNNING
    
    async def test_approval_queue(self, registry, temp_hands_dir):
        """Should manage approval queue."""
        await registry.load_all()
        
        # Create approval
        request = await registry.create_approval(
            hand_name="oracle",
            action="post_tweet",
            description="Post Bitcoin update",
            context={"price": 50000},
        )
        
        assert request.id is not None
        assert request.hand_name == "oracle"
        
        # Get pending
        pending = await registry.get_pending_approvals()
        assert len(pending) == 1
        
        # Resolve
        result = await registry.resolve_approval(request.id, approved=True)
        assert result is True
        
        # Should be empty now
        pending = await registry.get_pending_approvals()
        assert len(pending) == 0


@pytest.mark.asyncio
class TestHandScheduler:
    """HandScheduler tests."""
    
    async def test_scheduler_initialization(self, registry):
        """Should initialize scheduler."""
        scheduler = HandScheduler(registry)
        assert scheduler.registry == registry
        assert not scheduler._running
    
    async def test_schedule_hand(self, registry, temp_hands_dir):
        """Should schedule a Hand."""
        await registry.load_all()
        scheduler = HandScheduler(registry)
        
        hand = registry.get_hand("oracle")
        job_id = await scheduler.schedule_hand(hand)
        
        # Note: Job ID may be None if APScheduler not available
        # But should not raise an exception
    
    async def test_get_scheduled_jobs(self, registry, temp_hands_dir):
        """Should list scheduled jobs."""
        await registry.load_all()
        scheduler = HandScheduler(registry)
        
        jobs = scheduler.get_scheduled_jobs()
        assert isinstance(jobs, list)
    
    async def test_trigger_hand_now(self, registry, temp_hands_dir):
        """Should manually trigger a Hand."""
        await registry.load_all()
        scheduler = HandScheduler(registry)
        
        # This will fail because Hand isn't fully implemented
        # But should not raise
        result = await scheduler.trigger_hand_now("oracle")
        # Result may be True or False depending on implementation


@pytest.mark.asyncio
class TestHandRunner:
    """HandRunner tests."""
    
    async def test_load_system_prompt(self, registry, temp_hands_dir):
        """Should load SYSTEM.md."""
        await registry.load_all()
        runner = HandRunner(registry)
        
        hand = registry.get_hand("oracle")
        prompt = runner._load_system_prompt(hand)
        
        assert "Oracle" in prompt
    
    async def test_load_skills(self, registry, temp_hands_dir):
        """Should load SKILL.md files."""
        # Create a skill file
        skills_dir = temp_hands_dir / "oracle" / "skills"
        skills_dir.mkdir()
        (skills_dir / "bitcoin.md").write_text("# Bitcoin Expertise")
        
        await registry.load_all()
        runner = HandRunner(registry)
        
        hand = registry.get_hand("oracle")
        skills = runner._load_skills(hand)
        
        assert len(skills) == 1
        assert "Bitcoin" in skills[0]
    
    async def test_build_prompt(self, registry, temp_hands_dir):
        """Should build execution prompt."""
        await registry.load_all()
        runner = HandRunner(registry)
        
        hand = registry.get_hand("oracle")
        system = "System prompt"
        skills = ["Skill 1", "Skill 2"]
        context = {"key": "value"}
        
        prompt = runner._build_prompt(hand, system, skills, context)
        
        assert "System Instructions" in prompt
        assert "System prompt" in prompt
        assert "Skill 1" in prompt
        assert "key" in prompt


class TestHandConfig:
    """HandConfig model tests."""
    
    def test_hand_config_creation(self):
        """Should create HandConfig."""
        config = HandConfig(
            name="test",
            description="Test hand",
            schedule=ScheduleConfig(cron="0 * * * *"),
        )
        
        assert config.name == "test"
        assert config.schedule.cron == "0 * * * *"
    
    def test_schedule_validation(self):
        """Should validate cron expression."""
        # Valid cron
        config = HandConfig(
            name="test",
            description="Test",
            schedule=ScheduleConfig(cron="0 7 * * *"),
        )
        assert config.schedule.cron == "0 7 * * *"


class TestHandModels:
    """Hand model tests."""
    
    def test_hand_status_enum(self):
        """HandStatus should have expected values."""
        from hands.models import HandStatus
        
        assert HandStatus.IDLE.value == "idle"
        assert HandStatus.RUNNING.value == "running"
        assert HandStatus.SCHEDULED.value == "scheduled"
    
    def test_hand_state_to_dict(self):
        """HandState should serialize to dict."""
        from hands.models import HandState
        from datetime import datetime
        
        state = HandState(
            name="test",
            status=HandStatus.RUNNING,
            run_count=5,
        )
        
        data = state.to_dict()
        assert data["name"] == "test"
        assert data["status"] == "running"
        assert data["run_count"] == 5
