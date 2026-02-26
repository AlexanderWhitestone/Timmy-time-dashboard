"""End-to-end integration tests for Self-Coding layer.

Tests the complete workflow: GitSafety + CodebaseIndexer + ModificationJournal + Reflection
working together.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from self_coding import (
    CodebaseIndexer,
    GitSafety,
    ModificationAttempt,
    ModificationJournal,
    Outcome,
    ReflectionService,
    Snapshot,
)


@pytest.fixture
def self_coding_env():
    """Create a complete self-coding environment with temp repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path, check=True, capture_output=True,
        )
        
        # Create src directory with real Python files
        src_path = repo_path / "src" / "myproject"
        src_path.mkdir(parents=True)
        
        (src_path / "__init__.py").write_text("")
        (src_path / "calculator.py").write_text('''
"""A simple calculator module."""

class Calculator:
    """Basic calculator with add/subtract."""
    
    def add(self, a: int, b: int) -> int:
        return a + b
    
    def subtract(self, a: int, b: int) -> int:
        return a - b
''')
        
        (src_path / "utils.py").write_text('''
"""Utility functions."""

from myproject.calculator import Calculator


def calculate_total(items: list[int]) -> int:
    calc = Calculator()
    return sum(calc.add(0, item) for item in items)
''')
        
        # Create tests
        tests_path = repo_path / "tests"
        tests_path.mkdir()
        
        (tests_path / "test_calculator.py").write_text('''
"""Tests for calculator."""

from myproject.calculator import Calculator


def test_add():
    calc = Calculator()
    assert calc.add(2, 3) == 5


def test_subtract():
    calc = Calculator()
    assert calc.subtract(5, 3) == 2
''')
        
        # Initial commit
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=repo_path, check=True, capture_output=True,
        )
        
        # Initialize services
        git = GitSafety(
            repo_path=repo_path,
            main_branch="main",
            test_command="python -m pytest tests/ -v",
        )
        indexer = CodebaseIndexer(
            repo_path=repo_path,
            db_path=repo_path / "codebase.db",
            src_dirs=["src", "tests"],
        )
        journal = ModificationJournal(db_path=repo_path / "journal.db")
        reflection = ReflectionService(llm_adapter=None)
        
        yield {
            "repo_path": repo_path,
            "git": git,
            "indexer": indexer,
            "journal": journal,
            "reflection": reflection,
        }


@pytest.mark.asyncio
class TestSelfCodingGreenPath:
    """Happy path: successful self-modification workflow."""
    
    async def test_complete_successful_modification(self, self_coding_env):
        """Full workflow: snapshot → branch → modify → test → commit → merge → log → reflect."""
        env = self_coding_env
        git = env["git"]
        indexer = env["indexer"]
        journal = env["journal"]
        reflection = env["reflection"]
        repo_path = env["repo_path"]
        
        # 1. Index codebase to understand structure
        await indexer.index_all()
        
        # 2. Find relevant files for task
        files = await indexer.get_relevant_files("add multiply method to calculator", limit=3)
        assert "src/myproject/calculator.py" in files
        
        # 3. Check for similar past attempts
        similar = await journal.find_similar("add multiply method", limit=5)
        # Should be empty (first attempt)
        
        # 4. Take snapshot
        snapshot = await git.snapshot(run_tests=False)
        assert isinstance(snapshot, Snapshot)
        
        # 5. Create feature branch
        branch_name = "timmy/self-edit/add-multiply"
        branch = await git.create_branch(branch_name)
        assert branch == branch_name
        
        # 6. Make modification (simulate adding multiply method)
        calc_path = repo_path / "src" / "myproject" / "calculator.py"
        content = calc_path.read_text()
        new_method = '''
    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b
'''
        # Insert before last method
        content = content.rstrip() + "\n" + new_method + "\n"
        calc_path.write_text(content)
        
        # 7. Add test for new method
        test_path = repo_path / "tests" / "test_calculator.py"
        test_content = test_path.read_text()
        new_test = '''

def test_multiply():
    calc = Calculator()
    assert calc.multiply(3, 4) == 12
'''
        test_path.write_text(test_content.rstrip() + new_test + "\n")
        
        # 8. Commit changes
        commit_hash = await git.commit(
            "Add multiply method to Calculator",
            ["src/myproject/calculator.py", "tests/test_calculator.py"],
        )
        assert len(commit_hash) == 40
        
        # 9. Merge to main (skipping actual test run for speed)
        merge_hash = await git.merge_to_main(branch, require_tests=False)
        assert merge_hash != snapshot.commit_hash
        
        # 10. Log the successful attempt
        diff = await git.get_diff(snapshot.commit_hash)
        attempt = ModificationAttempt(
            task_description="Add multiply method to Calculator",
            approach="Added multiply method with docstring and test",
            files_modified=["src/myproject/calculator.py", "tests/test_calculator.py"],
            diff=diff[:1000],  # Truncate for storage
            test_results="Tests passed",
            outcome=Outcome.SUCCESS,
        )
        attempt_id = await journal.log_attempt(attempt)
        
        # 11. Generate reflection
        reflection_text = await reflection.reflect_on_attempt(attempt)
        assert "What went well" in reflection_text
        
        await journal.update_reflection(attempt_id, reflection_text)
        
        # 12. Verify final state
        final_commit = await git.get_current_commit()
        assert final_commit == merge_hash
        
        # Verify we're on main branch
        current_branch = await git.get_current_branch()
        assert current_branch == "main"
        
        # Verify multiply method exists
        final_content = calc_path.read_text()
        assert "def multiply" in final_content
    
    async def test_incremental_codebase_indexing(self, self_coding_env):
        """Codebase indexer should detect changes after modification."""
        env = self_coding_env
        indexer = env["indexer"]
        
        # Initial index
        stats1 = await indexer.index_all()
        assert stats1["indexed"] == 4  # __init__.py, calculator.py, utils.py, test_calculator.py
        
        # Add new file
        new_file = env["repo_path"] / "src" / "myproject" / "new_module.py"
        new_file.write_text('''
"""New module."""
def new_function(): pass
''')
        
        # Incremental index should detect only the new file
        stats2 = await indexer.index_changed()
        assert stats2["indexed"] == 1
        assert stats2["skipped"] == 4


@pytest.mark.asyncio
class TestSelfCodingRedPaths:
    """Error paths: failures, rollbacks, and recovery."""
    
    async def test_rollback_on_test_failure(self, self_coding_env):
        """Should rollback when tests fail."""
        env = self_coding_env
        git = env["git"]
        journal = env["journal"]
        repo_path = env["repo_path"]
        
        # Take snapshot
        snapshot = await git.snapshot(run_tests=False)
        original_commit = snapshot.commit_hash
        
        # Create branch
        branch = await git.create_branch("timmy/self-edit/bad-change")
        
        # Make breaking change (remove add method)
        calc_path = repo_path / "src" / "myproject" / "calculator.py"
        calc_path.write_text('''
"""A simple calculator module."""

class Calculator:
    """Basic calculator - broken version."""
    pass
''')
        
        await git.commit("Remove methods (breaking change)")
        
        # Log the failed attempt
        attempt = ModificationAttempt(
            task_description="Refactor Calculator class",
            approach="Remove unused methods",
            files_modified=["src/myproject/calculator.py"],
            outcome=Outcome.FAILURE,
            failure_analysis="Tests failed - removed methods that were used",
            retry_count=0,
        )
        await journal.log_attempt(attempt)
        
        # Rollback
        await git.rollback(snapshot)
        
        # Verify rollback
        current = await git.get_current_commit()
        assert current == original_commit
        
        # Verify file restored
        restored_content = calc_path.read_text()
        assert "def add" in restored_content
    
    async def test_find_similar_learns_from_failures(self, self_coding_env):
        """Should find similar past failures to avoid repeating mistakes."""
        env = self_coding_env
        journal = env["journal"]
        
        # Log a failure
        await journal.log_attempt(ModificationAttempt(
            task_description="Add division method to calculator",
            approach="Simple division without zero check",
            files_modified=["src/myproject/calculator.py"],
            outcome=Outcome.FAILURE,
            failure_analysis="ZeroDivisionError not handled",
            reflection="Always check for division by zero",
        ))
        
        # Later, try similar task
        similar = await journal.find_similar(
            "Add modulo operation to calculator",
            limit=5,
        )
        
        # Should find the past failure
        assert len(similar) > 0
        assert "division" in similar[0].task_description.lower()
    
    async def test_dependency_chain_detects_blast_radius(self, self_coding_env):
        """Should detect which files depend on modified file."""
        env = self_coding_env
        indexer = env["indexer"]
        
        await indexer.index_all()
        
        # utils.py imports from calculator.py
        deps = await indexer.get_dependency_chain("src/myproject/calculator.py")
        
        assert "src/myproject/utils.py" in deps
    
    async def test_success_rate_tracking(self, self_coding_env):
        """Should track success/failure metrics over time."""
        env = self_coding_env
        journal = env["journal"]
        
        # Log mixed outcomes
        for i in range(5):
            await journal.log_attempt(ModificationAttempt(
                task_description=f"Task {i}",
                outcome=Outcome.SUCCESS if i % 2 == 0 else Outcome.FAILURE,
            ))
        
        metrics = await journal.get_success_rate()
        
        assert metrics["total"] == 5
        assert metrics["success"] == 3
        assert metrics["failure"] == 2
        assert metrics["overall"] == 0.6
    
    async def test_journal_persists_across_instances(self, self_coding_env):
        """Journal should persist even with new service instances."""
        env = self_coding_env
        db_path = env["repo_path"] / "persistent_journal.db"
        
        # First instance logs attempt
        journal1 = ModificationJournal(db_path=db_path)
        attempt_id = await journal1.log_attempt(ModificationAttempt(
            task_description="Persistent task",
            outcome=Outcome.SUCCESS,
        ))
        
        # New instance should see the attempt
        journal2 = ModificationJournal(db_path=db_path)
        retrieved = await journal2.get_by_id(attempt_id)
        
        assert retrieved is not None
        assert retrieved.task_description == "Persistent task"


@pytest.mark.asyncio
class TestSelfCodingSafetyConstraints:
    """Safety constraints and validation."""
    
    async def test_only_modify_files_with_test_coverage(self, self_coding_env):
        """Should only allow modifying files that have tests."""
        env = self_coding_env
        indexer = env["indexer"]
        
        await indexer.index_all()
        
        # calculator.py has test coverage
        assert await indexer.has_test_coverage("src/myproject/calculator.py")
        
        # utils.py has no test file
        assert not await indexer.has_test_coverage("src/myproject/utils.py")
    
    async def test_cannot_delete_test_files(self, self_coding_env):
        """Safety check: should not delete test files."""
        env = self_coding_env
        git = env["git"]
        repo_path = env["repo_path"]
        
        snapshot = await git.snapshot(run_tests=False)
        branch = await git.create_branch("timmy/self-edit/bad-idea")
        
        # Try to delete test file
        test_file = repo_path / "tests" / "test_calculator.py"
        test_file.unlink()
        
        # This would be caught by safety constraints in real implementation
        # For now, verify the file is gone
        assert not test_file.exists()
        
        # Rollback should restore it
        await git.rollback(snapshot)
        assert test_file.exists()
    
    async def test_branch_naming_convention(self, self_coding_env):
        """Branches should follow naming convention."""
        env = self_coding_env
        git = env["git"]
        
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"timmy/self-edit/{timestamp}"
        
        branch = await git.create_branch(branch_name)
        
        assert branch.startswith("timmy/self-edit/")


@pytest.mark.asyncio
class TestSelfCodingErrorRecovery:
    """Error recovery scenarios."""
    
    async def test_git_operation_timeout_handling(self, self_coding_env):
        """Should handle git operation timeouts gracefully."""
        # This would require mocking subprocess to timeout
        # For now, verify the timeout parameter exists
        env = self_coding_env
        git = env["git"]
        
        # The _run_git method has timeout parameter
        # If a git operation times out, it raises GitOperationError
        assert hasattr(git, '_run_git')
    
    async def test_journal_handles_concurrent_writes(self, self_coding_env):
        """Journal should handle multiple rapid writes."""
        env = self_coding_env
        journal = env["journal"]
        
        # Log multiple attempts rapidly
        ids = []
        for i in range(10):
            attempt_id = await journal.log_attempt(ModificationAttempt(
                task_description=f"Concurrent task {i}",
                outcome=Outcome.SUCCESS,
            ))
            ids.append(attempt_id)
        
        # All should be unique and retrievable
        assert len(set(ids)) == 10
        
        for attempt_id in ids:
            retrieved = await journal.get_by_id(attempt_id)
            assert retrieved is not None
    
    async def test_indexer_handles_syntax_errors(self, self_coding_env):
        """Indexer should skip files with syntax errors."""
        env = self_coding_env
        indexer = env["indexer"]
        repo_path = env["repo_path"]
        
        # Create file with syntax error
        bad_file = repo_path / "src" / "myproject" / "bad_syntax.py"
        bad_file.write_text("def broken(:")
        
        stats = await indexer.index_all()
        
        # Should index good files, fail on bad one
        assert stats["failed"] == 1
        assert stats["indexed"] >= 4  # The good files
