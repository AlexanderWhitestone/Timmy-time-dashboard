"""Tests for Oracle and Sentinel Hands.

Validates the first two autonomous Hands work with the infrastructure.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from hands import HandRegistry
from hands.models import HandConfig, HandStatus


@pytest.fixture
def hands_dir():
    """Return the actual hands directory."""
    return Path("hands")


@pytest.mark.asyncio
class TestOracleHand:
    """Oracle Hand validation tests."""
    
    async def test_oracle_hand_exists(self, hands_dir):
        """Oracle hand directory should exist."""
        oracle_dir = hands_dir / "oracle"
        assert oracle_dir.exists()
        assert oracle_dir.is_dir()
    
    async def test_oracle_hand_toml_valid(self, hands_dir):
        """Oracle HAND.toml should be valid."""
        toml_path = hands_dir / "oracle" / "HAND.toml"
        assert toml_path.exists()
        
        # Should parse without errors
        import tomllib
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        
        assert config["hand"]["name"] == "oracle"
        assert config["hand"]["schedule"] == "0 7,19 * * *"
        assert config["hand"]["enabled"] is True
    
    async def test_oracle_system_md_exists(self, hands_dir):
        """Oracle SYSTEM.md should exist."""
        system_path = hands_dir / "oracle" / "SYSTEM.md"
        assert system_path.exists()
        
        content = system_path.read_text()
        assert "Oracle" in content
        assert "Bitcoin" in content
    
    async def test_oracle_skills_exist(self, hands_dir):
        """Oracle should have skills."""
        skills_dir = hands_dir / "oracle" / "skills"
        assert skills_dir.exists()
        
        # Should have technical analysis skill
        ta_skill = skills_dir / "technical_analysis.md"
        assert ta_skill.exists()
    
    async def test_oracle_loads_in_registry(self, hands_dir):
        """Oracle should load in HandRegistry."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            
            hands = await registry.load_all()
            
            assert "oracle" in hands
            hand = hands["oracle"]
            
            assert hand.name == "oracle"
            assert "Bitcoin" in hand.description
            assert hand.schedule is not None
            assert hand.schedule.cron == "0 7,19 * * *"
            assert hand.enabled is True


@pytest.mark.asyncio
class TestSentinelHand:
    """Sentinel Hand validation tests."""
    
    async def test_sentinel_hand_exists(self, hands_dir):
        """Sentinel hand directory should exist."""
        sentinel_dir = hands_dir / "sentinel"
        assert sentinel_dir.exists()
        assert sentinel_dir.is_dir()
    
    async def test_sentinel_hand_toml_valid(self, hands_dir):
        """Sentinel HAND.toml should be valid."""
        toml_path = hands_dir / "sentinel" / "HAND.toml"
        assert toml_path.exists()
        
        import tomllib
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        
        assert config["hand"]["name"] == "sentinel"
        assert config["hand"]["schedule"] == "*/15 * * * *"
        assert config["hand"]["enabled"] is True
    
    async def test_sentinel_system_md_exists(self, hands_dir):
        """Sentinel SYSTEM.md should exist."""
        system_path = hands_dir / "sentinel" / "SYSTEM.md"
        assert system_path.exists()
        
        content = system_path.read_text()
        assert "Sentinel" in content
        assert "health" in content.lower()
    
    async def test_sentinel_skills_exist(self, hands_dir):
        """Sentinel should have skills."""
        skills_dir = hands_dir / "sentinel" / "skills"
        assert skills_dir.exists()
        
        patterns_skill = skills_dir / "monitoring_patterns.md"
        assert patterns_skill.exists()
    
    async def test_sentinel_loads_in_registry(self, hands_dir):
        """Sentinel should load in HandRegistry."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            
            hands = await registry.load_all()
            
            assert "sentinel" in hands
            hand = hands["sentinel"]
            
            assert hand.name == "sentinel"
            assert "health" in hand.description.lower()
            assert hand.schedule is not None
            assert hand.schedule.cron == "*/15 * * * *"


@pytest.mark.asyncio
class TestHandSchedules:
    """Validate Hand schedules are correct."""
    
    async def test_oracle_runs_twice_daily(self, hands_dir):
        """Oracle should run at 7am and 7pm."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("oracle")
            # Cron: 0 7,19 * * * = minute 0, hours 7 and 19
            assert hand.schedule.cron == "0 7,19 * * *"
    
    async def test_sentinel_runs_every_15_minutes(self, hands_dir):
        """Sentinel should run every 15 minutes."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("sentinel")
            # Cron: */15 * * * * = every 15 minutes
            assert hand.schedule.cron == "*/15 * * * *"


@pytest.mark.asyncio
class TestHandApprovalGates:
    """Validate approval gates are configured."""
    
    async def test_oracle_has_approval_gates(self, hands_dir):
        """Oracle should have approval gates defined."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("oracle")
            # Should have at least one approval gate
            assert len(hand.approval_gates) > 0
    
    async def test_sentinel_has_approval_gates(self, hands_dir):
        """Sentinel should have approval gates defined."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("sentinel")
            # Should have approval gates for restart and alert
            assert len(hand.approval_gates) >= 1
