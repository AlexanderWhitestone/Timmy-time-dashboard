"""Tests for Modification Journal.

Tests logging, querying, and metrics for self-modification attempts.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from self_coding.modification_journal import (
    ModificationAttempt,
    ModificationJournal,
    Outcome,
)


@pytest.fixture
def temp_journal():
    """Create a ModificationJournal with temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "journal.db"
        journal = ModificationJournal(db_path=db_path)
        yield journal


@pytest.mark.asyncio
class TestModificationJournalLogging:
    """Logging modification attempts."""
    
    async def test_log_attempt_success(self, temp_journal):
        """Should log a successful attempt."""
        attempt = ModificationAttempt(
            task_description="Add error handling to health endpoint",
            approach="Use try/except block",
            files_modified=["src/app.py"],
            diff="@@ -1,3 +1,7 @@...",
            test_results="1 passed",
            outcome=Outcome.SUCCESS,
        )
        
        attempt_id = await temp_journal.log_attempt(attempt)
        
        assert attempt_id > 0
    
    async def test_log_attempt_failure(self, temp_journal):
        """Should log a failed attempt."""
        attempt = ModificationAttempt(
            task_description="Refactor database layer",
            approach="Extract connection pool",
            files_modified=["src/db.py", "src/models.py"],
            diff="@@ ...",
            test_results="2 failed",
            outcome=Outcome.FAILURE,
            failure_analysis="Circular dependency introduced",
            retry_count=2,
        )
        
        attempt_id = await temp_journal.log_attempt(attempt)
        
        # Retrieve and verify
        retrieved = await temp_journal.get_by_id(attempt_id)
        assert retrieved is not None
        assert retrieved.outcome == Outcome.FAILURE
        assert retrieved.failure_analysis == "Circular dependency introduced"
        assert retrieved.retry_count == 2


@pytest.mark.asyncio
class TestModificationJournalRetrieval:
    """Retrieving logged attempts."""
    
    async def test_get_by_id(self, temp_journal):
        """Should retrieve attempt by ID."""
        attempt = ModificationAttempt(
            task_description="Fix bug",
            outcome=Outcome.SUCCESS,
        )
        
        attempt_id = await temp_journal.log_attempt(attempt)
        retrieved = await temp_journal.get_by_id(attempt_id)
        
        assert retrieved is not None
        assert retrieved.task_description == "Fix bug"
        assert retrieved.id == attempt_id
    
    async def test_get_by_id_not_found(self, temp_journal):
        """Should return None for non-existent ID."""
        result = await temp_journal.get_by_id(9999)
        
        assert result is None
    
    async def test_find_similar_basic(self, temp_journal):
        """Should find similar attempts by keyword."""
        # Log some attempts
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Add error handling to API endpoints",
            outcome=Outcome.SUCCESS,
        ))
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Add logging to database queries",
            outcome=Outcome.SUCCESS,
        ))
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Fix CSS styling on homepage",
            outcome=Outcome.FAILURE,
        ))
        
        # Search for error handling
        similar = await temp_journal.find_similar("error handling in endpoints", limit=3)
        
        assert len(similar) > 0
        # Should find the API error handling attempt first
        assert "error" in similar[0].task_description.lower()
    
    async def test_find_similar_filter_outcome(self, temp_journal):
        """Should filter by outcome when specified."""
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Database optimization",
            outcome=Outcome.SUCCESS,
        ))
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Database refactoring",
            outcome=Outcome.FAILURE,
        ))
        
        # Search only for successes
        similar = await temp_journal.find_similar(
            "database work",
            include_outcomes=[Outcome.SUCCESS],
        )
        
        assert len(similar) == 1
        assert similar[0].outcome == Outcome.SUCCESS
    
    async def test_find_similar_empty(self, temp_journal):
        """Should return empty list when no matches."""
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Fix bug",
            outcome=Outcome.SUCCESS,
        ))
        
        similar = await temp_journal.find_similar("xyzqwerty unicorn astronaut", limit=5)
        
        assert similar == []


@pytest.mark.asyncio
class TestModificationJournalMetrics:
    """Success rate metrics."""
    
    async def test_get_success_rate_empty(self, temp_journal):
        """Should handle empty journal."""
        metrics = await temp_journal.get_success_rate()
        
        assert metrics["overall"] == 0.0
        assert metrics["total"] == 0
    
    async def test_get_success_rate_calculated(self, temp_journal):
        """Should calculate success rate correctly."""
        # Log various outcomes
        for _ in range(5):
            await temp_journal.log_attempt(ModificationAttempt(
                task_description="Success task",
                outcome=Outcome.SUCCESS,
            ))
        for _ in range(3):
            await temp_journal.log_attempt(ModificationAttempt(
                task_description="Failure task",
                outcome=Outcome.FAILURE,
            ))
        for _ in range(2):
            await temp_journal.log_attempt(ModificationAttempt(
                task_description="Rollback task",
                outcome=Outcome.ROLLBACK,
            ))
        
        metrics = await temp_journal.get_success_rate()
        
        assert metrics["success"] == 5
        assert metrics["failure"] == 3
        assert metrics["rollback"] == 2
        assert metrics["total"] == 10
        assert metrics["overall"] == 0.5  # 5/10
    
    async def test_get_recent_failures(self, temp_journal):
        """Should get recent failures."""
        # Log failures and successes (last one is most recent)
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Rollback attempt",
            outcome=Outcome.ROLLBACK,
        ))
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Success",
            outcome=Outcome.SUCCESS,
        ))
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Failed attempt",
            outcome=Outcome.FAILURE,
        ))
        
        failures = await temp_journal.get_recent_failures(limit=10)
        
        assert len(failures) == 2
        # Most recent first (Failure was logged last)
        assert failures[0].outcome == Outcome.FAILURE
        assert failures[1].outcome == Outcome.ROLLBACK


@pytest.mark.asyncio
class TestModificationJournalUpdates:
    """Updating logged attempts."""
    
    async def test_update_reflection(self, temp_journal):
        """Should update reflection for an attempt."""
        attempt = ModificationAttempt(
            task_description="Test task",
            outcome=Outcome.SUCCESS,
        )
        
        attempt_id = await temp_journal.log_attempt(attempt)
        
        # Update reflection
        success = await temp_journal.update_reflection(
            attempt_id,
            "This worked well because...",
        )
        
        assert success is True
        
        # Verify
        retrieved = await temp_journal.get_by_id(attempt_id)
        assert retrieved.reflection == "This worked well because..."
    
    async def test_update_reflection_not_found(self, temp_journal):
        """Should return False for non-existent ID."""
        success = await temp_journal.update_reflection(9999, "Reflection")
        
        assert success is False


@pytest.mark.asyncio
class TestModificationJournalFileTracking:
    """Tracking attempts by file."""
    
    async def test_get_attempts_for_file(self, temp_journal):
        """Should find all attempts that modified a file."""
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Fix app.py",
            files_modified=["src/app.py", "src/config.py"],
            outcome=Outcome.SUCCESS,
        ))
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Update config only",
            files_modified=["src/config.py"],
            outcome=Outcome.SUCCESS,
        ))
        await temp_journal.log_attempt(ModificationAttempt(
            task_description="Other file",
            files_modified=["src/other.py"],
            outcome=Outcome.SUCCESS,
        ))
        
        app_attempts = await temp_journal.get_attempts_for_file("src/app.py")
        
        assert len(app_attempts) == 1
        assert "src/app.py" in app_attempts[0].files_modified


@pytest.mark.asyncio
class TestModificationJournalIntegration:
    """Full workflow integration tests."""
    
    async def test_full_workflow(self, temp_journal):
        """Complete workflow: log, find similar, get metrics."""
        # Log some attempts
        for i in range(3):
            await temp_journal.log_attempt(ModificationAttempt(
                task_description=f"Database optimization {i}",
                approach="Add indexes",
                files_modified=["src/db.py"],
                outcome=Outcome.SUCCESS if i % 2 == 0 else Outcome.FAILURE,
            ))
        
        # Find similar
        similar = await temp_journal.find_similar("optimize database queries", limit=5)
        assert len(similar) == 3
        
        # Get success rate
        metrics = await temp_journal.get_success_rate()
        assert metrics["total"] == 3
        assert metrics["success"] == 2
        
        # Get recent failures
        failures = await temp_journal.get_recent_failures(limit=5)
        assert len(failures) == 1
        
        # Get attempts for file
        file_attempts = await temp_journal.get_attempts_for_file("src/db.py")
        assert len(file_attempts) == 3
    
    async def test_persistence(self):
        """Should persist across instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "persist.db"
            
            # First instance
            journal1 = ModificationJournal(db_path=db_path)
            attempt_id = await journal1.log_attempt(ModificationAttempt(
                task_description="Persistent attempt",
                outcome=Outcome.SUCCESS,
            ))
            
            # Second instance with same database
            journal2 = ModificationJournal(db_path=db_path)
            retrieved = await journal2.get_by_id(attempt_id)
            
            assert retrieved is not None
            assert retrieved.task_description == "Persistent attempt"
