"""Tests for Phase 5 Additional Hands (Scout, Scribe, Ledger, Weaver).

Validates the new Hands load correctly and have proper configuration.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from hands import HandRegistry
from hands.models import HandStatus


@pytest.fixture
def hands_dir():
    """Return the actual hands directory."""
    return Path("hands")


@pytest.mark.asyncio
class TestScoutHand:
    """Scout Hand validation tests."""
    
    async def test_scout_hand_exists(self, hands_dir):
        """Scout hand directory should exist."""
        scout_dir = hands_dir / "scout"
        assert scout_dir.exists()
        assert scout_dir.is_dir()
    
    async def test_scout_hand_toml_valid(self, hands_dir):
        """Scout HAND.toml should be valid."""
        toml_path = hands_dir / "scout" / "HAND.toml"
        assert toml_path.exists()
        
        import tomllib
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        
        assert config["hand"]["name"] == "scout"
        assert config["hand"]["schedule"] == "0 * * * *"  # Hourly
        assert config["hand"]["enabled"] is True
    
    async def test_scout_system_md_exists(self, hands_dir):
        """Scout SYSTEM.md should exist."""
        system_path = hands_dir / "scout" / "SYSTEM.md"
        assert system_path.exists()
        
        content = system_path.read_text()
        assert "Scout" in content
        assert "OSINT" in content
    
    async def test_scout_loads_in_registry(self, hands_dir):
        """Scout should load in HandRegistry."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            
            hands = await registry.load_all()
            
            assert "scout" in hands
            hand = hands["scout"]
            
            assert hand.name == "scout"
            assert "OSINT" in hand.description or "intelligence" in hand.description.lower()
            assert hand.schedule is not None
            assert hand.schedule.cron == "0 * * * *"


@pytest.mark.asyncio
class TestScribeHand:
    """Scribe Hand validation tests."""
    
    async def test_scribe_hand_exists(self, hands_dir):
        """Scribe hand directory should exist."""
        scribe_dir = hands_dir / "scribe"
        assert scribe_dir.exists()
    
    async def test_scribe_hand_toml_valid(self, hands_dir):
        """Scribe HAND.toml should be valid."""
        toml_path = hands_dir / "scribe" / "HAND.toml"
        assert toml_path.exists()
        
        import tomllib
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        
        assert config["hand"]["name"] == "scribe"
        assert config["hand"]["schedule"] == "0 9 * * *"  # Daily 9am
        assert config["hand"]["enabled"] is True
    
    async def test_scribe_system_md_exists(self, hands_dir):
        """Scribe SYSTEM.md should exist."""
        system_path = hands_dir / "scribe" / "SYSTEM.md"
        assert system_path.exists()
        
        content = system_path.read_text()
        assert "Scribe" in content
        assert "content" in content.lower()
    
    async def test_scribe_loads_in_registry(self, hands_dir):
        """Scribe should load in HandRegistry."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            
            hands = await registry.load_all()
            
            assert "scribe" in hands
            hand = hands["scribe"]
            
            assert hand.name == "scribe"
            assert hand.schedule.cron == "0 9 * * *"


@pytest.mark.asyncio
class TestLedgerHand:
    """Ledger Hand validation tests."""
    
    async def test_ledger_hand_exists(self, hands_dir):
        """Ledger hand directory should exist."""
        ledger_dir = hands_dir / "ledger"
        assert ledger_dir.exists()
    
    async def test_ledger_hand_toml_valid(self, hands_dir):
        """Ledger HAND.toml should be valid."""
        toml_path = hands_dir / "ledger" / "HAND.toml"
        assert toml_path.exists()
        
        import tomllib
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        
        assert config["hand"]["name"] == "ledger"
        assert config["hand"]["schedule"] == "0 */6 * * *"  # Every 6 hours
        assert config["hand"]["enabled"] is True
    
    async def test_ledger_system_md_exists(self, hands_dir):
        """Ledger SYSTEM.md should exist."""
        system_path = hands_dir / "ledger" / "SYSTEM.md"
        assert system_path.exists()
        
        content = system_path.read_text()
        assert "Ledger" in content
        assert "treasury" in content.lower()
    
    async def test_ledger_loads_in_registry(self, hands_dir):
        """Ledger should load in HandRegistry."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            
            hands = await registry.load_all()
            
            assert "ledger" in hands
            hand = hands["ledger"]
            
            assert hand.name == "ledger"
            assert "treasury" in hand.description.lower() or "bitcoin" in hand.description.lower()
            assert hand.schedule.cron == "0 */6 * * *"


@pytest.mark.asyncio
class TestWeaverHand:
    """Weaver Hand validation tests."""
    
    async def test_weaver_hand_exists(self, hands_dir):
        """Weaver hand directory should exist."""
        weaver_dir = hands_dir / "weaver"
        assert weaver_dir.exists()
    
    async def test_weaver_hand_toml_valid(self, hands_dir):
        """Weaver HAND.toml should be valid."""
        toml_path = hands_dir / "weaver" / "HAND.toml"
        assert toml_path.exists()
        
        import tomllib
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        
        assert config["hand"]["name"] == "weaver"
        assert config["hand"]["schedule"] == "0 10 * * 0"  # Sunday 10am
        assert config["hand"]["enabled"] is True
    
    async def test_weaver_system_md_exists(self, hands_dir):
        """Weaver SYSTEM.md should exist."""
        system_path = hands_dir / "weaver" / "SYSTEM.md"
        assert system_path.exists()
        
        content = system_path.read_text()
        assert "Weaver" in content
        assert "creative" in content.lower()
    
    async def test_weaver_loads_in_registry(self, hands_dir):
        """Weaver should load in HandRegistry."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            
            hands = await registry.load_all()
            
            assert "weaver" in hands
            hand = hands["weaver"]
            
            assert hand.name == "weaver"
            assert hand.schedule.cron == "0 10 * * 0"


@pytest.mark.asyncio
class TestPhase5Schedules:
    """Validate all Phase 5 Hand schedules."""
    
    async def test_scout_runs_hourly(self, hands_dir):
        """Scout should run every hour."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("scout")
            assert hand.schedule.cron == "0 * * * *"
    
    async def test_scribe_runs_daily(self, hands_dir):
        """Scribe should run daily at 9am."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("scribe")
            assert hand.schedule.cron == "0 9 * * *"
    
    async def test_ledger_runs_6_hours(self, hands_dir):
        """Ledger should run every 6 hours."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("ledger")
            assert hand.schedule.cron == "0 */6 * * *"
    
    async def test_weaver_runs_weekly(self, hands_dir):
        """Weaver should run weekly on Sunday."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("weaver")
            assert hand.schedule.cron == "0 10 * * 0"


@pytest.mark.asyncio
class TestPhase5ApprovalGates:
    """Validate Phase 5 Hands have approval gates."""
    
    async def test_scout_has_approval_gates(self, hands_dir):
        """Scout should have approval gates."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("scout")
            assert len(hand.approval_gates) >= 1
    
    async def test_scribe_has_approval_gates(self, hands_dir):
        """Scribe should have approval gates."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("scribe")
            assert len(hand.approval_gates) >= 1
    
    async def test_ledger_has_approval_gates(self, hands_dir):
        """Ledger should have approval gates."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("ledger")
            assert len(hand.approval_gates) >= 1
    
    async def test_weaver_has_approval_gates(self, hands_dir):
        """Weaver should have approval gates."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            await registry.load_all()
            
            hand = registry.get_hand("weaver")
            assert len(hand.approval_gates) >= 1


@pytest.mark.asyncio
class TestAllHandsLoad:
    """Verify all 6 Hands load together."""
    
    async def test_all_hands_present(self, hands_dir):
        """All 6 Hands should load without errors."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            registry = HandRegistry(hands_dir=hands_dir, db_path=db_path)
            
            hands = await registry.load_all()
            
            # All 6 Hands should be present
            expected = {"oracle", "sentinel", "scout", "scribe", "ledger", "weaver"}
            assert expected.issubset(set(hands.keys()))
