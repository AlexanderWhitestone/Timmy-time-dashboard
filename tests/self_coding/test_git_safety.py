"""Tests for Git Safety Layer.

Uses temporary git repositories to test snapshot/rollback/merge workflows
without affecting the actual Timmy repository.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from self_coding.git_safety import (
    GitSafety,
    GitDirtyWorkingDirectoryError,
    GitNotRepositoryError,
    GitOperationError,
    Snapshot,
)


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial file and commit
        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        
        # Rename master to main if needed
        result = subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=repo_path,
            capture_output=True,
        )
        
        yield repo_path


@pytest.fixture
def git_safety(temp_git_repo):
    """Create GitSafety instance for temp repo."""
    safety = GitSafety(
        repo_path=temp_git_repo,
        main_branch="main",
        test_command="echo 'No tests configured'",  # Fake test command
    )
    return safety


@pytest.mark.asyncio
class TestGitSafetyBasics:
    """Basic git operations."""
    
    async def test_init_with_valid_repo(self, temp_git_repo):
        """Should initialize successfully with valid git repo."""
        safety = GitSafety(repo_path=temp_git_repo)
        assert safety.repo_path == temp_git_repo.resolve()
        assert safety.main_branch == "main"
    
    async def test_init_with_invalid_repo(self):
        """Should raise GitNotRepositoryError for non-repo path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(GitNotRepositoryError):
                GitSafety(repo_path=tmpdir)
    
    async def test_is_clean_clean_repo(self, git_safety, temp_git_repo):
        """Should return True for clean repo."""
        safety = git_safety
        assert await safety.is_clean() is True
    
    async def test_is_clean_dirty_repo(self, git_safety, temp_git_repo):
        """Should return False when there are uncommitted changes."""
        safety = git_safety
        # Create uncommitted file
        (temp_git_repo / "dirty.txt").write_text("dirty")
        assert await safety.is_clean() is False
    
    async def test_get_current_branch(self, git_safety):
        """Should return current branch name."""
        safety = git_safety
        branch = await safety.get_current_branch()
        assert branch == "main"
    
    async def test_get_current_commit(self, git_safety):
        """Should return valid commit hash."""
        safety = git_safety
        commit = await safety.get_current_commit()
        assert len(commit) == 40  # Full SHA-1 hash
        assert all(c in "0123456789abcdef" for c in commit)


@pytest.mark.asyncio
class TestGitSafetySnapshot:
    """Snapshot functionality."""
    
    async def test_snapshot_returns_snapshot_object(self, git_safety):
        """Should return Snapshot with all fields populated."""
        safety = git_safety
        snapshot = await safety.snapshot(run_tests=False)
        
        assert isinstance(snapshot, Snapshot)
        assert len(snapshot.commit_hash) == 40
        assert snapshot.branch == "main"
        assert snapshot.timestamp is not None
        assert snapshot.clean is True
    
    async def test_snapshot_captures_clean_status(self, git_safety, temp_git_repo):
        """Should correctly capture clean/dirty status."""
        safety = git_safety
        
        # Clean snapshot
        clean_snapshot = await safety.snapshot(run_tests=False)
        assert clean_snapshot.clean is True
        
        # Dirty snapshot
        (temp_git_repo / "dirty.txt").write_text("dirty")
        dirty_snapshot = await safety.snapshot(run_tests=False)
        assert dirty_snapshot.clean is False
    
    async def test_snapshot_with_tests(self, git_safety, temp_git_repo):
        """Should run tests and capture status."""
        # Create a passing test
        (temp_git_repo / "test_pass.py").write_text("""
def test_pass():
    assert True
""")
        safety = GitSafety(
            repo_path=temp_git_repo,
            test_command="python -m pytest test_pass.py -v",
        )
        
        snapshot = await safety.snapshot(run_tests=True)
        assert snapshot.test_status is True
        assert "passed" in snapshot.test_output.lower() or "no tests" not in snapshot.test_output


@pytest.mark.asyncio
class TestGitSafetyBranching:
    """Branch creation and management."""
    
    async def test_create_branch(self, git_safety):
        """Should create and checkout new branch."""
        safety = git_safety
        
        branch_name = "timmy/self-edit/test"
        result = await safety.create_branch(branch_name)
        
        assert result == branch_name
        assert await safety.get_current_branch() == branch_name
    
    async def test_create_branch_from_main(self, git_safety, temp_git_repo):
        """New branch should start from main."""
        safety = git_safety
        
        main_commit = await safety.get_current_commit()
        
        await safety.create_branch("feature-branch")
        branch_commit = await safety.get_current_commit()
        
        assert branch_commit == main_commit


@pytest.mark.asyncio
class TestGitSafetyCommit:
    """Commit operations."""
    
    async def test_commit_specific_files(self, git_safety, temp_git_repo):
        """Should commit only specified files."""
        safety = git_safety
        
        # Create two files
        (temp_git_repo / "file1.txt").write_text("content1")
        (temp_git_repo / "file2.txt").write_text("content2")
        
        # Commit only file1
        commit_hash = await safety.commit("Add file1", ["file1.txt"])
        
        assert len(commit_hash) == 40
        
        # file2 should still be uncommitted
        assert await safety.is_clean() is False
    
    async def test_commit_all_changes(self, git_safety, temp_git_repo):
        """Should commit all changes when no files specified."""
        safety = git_safety
        
        (temp_git_repo / "new.txt").write_text("new content")
        
        commit_hash = await safety.commit("Add new file")
        
        assert len(commit_hash) == 40
        assert await safety.is_clean() is True
    
    async def test_commit_no_changes(self, git_safety):
        """Should handle commit with no changes gracefully."""
        safety = git_safety
        
        commit_hash = await safety.commit("No changes")
        
        # Should return current commit when no changes
        current = await safety.get_current_commit()
        assert commit_hash == current


@pytest.mark.asyncio
class TestGitSafetyDiff:
    """Diff operations."""
    
    async def test_get_diff(self, git_safety, temp_git_repo):
        """Should return diff between commits."""
        safety = git_safety
        
        original_commit = await safety.get_current_commit()
        
        # Make a change and commit
        (temp_git_repo / "new.txt").write_text("new content")
        await safety.commit("Add new file")
        
        new_commit = await safety.get_current_commit()
        
        diff = await safety.get_diff(original_commit, new_commit)
        
        assert "new.txt" in diff
        assert "new content" in diff
    
    async def test_get_modified_files(self, git_safety, temp_git_repo):
        """Should list modified files."""
        safety = git_safety
        
        original_commit = await safety.get_current_commit()
        
        (temp_git_repo / "file1.txt").write_text("content")
        (temp_git_repo / "file2.txt").write_text("content")
        await safety.commit("Add files")
        
        files = await safety.get_modified_files(original_commit)
        
        assert "file1.txt" in files
        assert "file2.txt" in files


@pytest.mark.asyncio
class TestGitSafetyRollback:
    """Rollback functionality."""
    
    async def test_rollback_to_snapshot(self, git_safety, temp_git_repo):
        """Should rollback to snapshot state."""
        safety = git_safety
        
        # Take snapshot
        snapshot = await safety.snapshot(run_tests=False)
        original_commit = snapshot.commit_hash
        
        # Make change and commit
        (temp_git_repo / "feature.txt").write_text("feature")
        await safety.commit("Add feature")
        
        # Verify we're on new commit
        new_commit = await safety.get_current_commit()
        assert new_commit != original_commit
        
        # Rollback
        rolled_back = await safety.rollback(snapshot)
        
        assert rolled_back == original_commit
        assert await safety.get_current_commit() == original_commit
    
    async def test_rollback_discards_uncommitted_changes(self, git_safety, temp_git_repo):
        """Rollback should discard uncommitted changes."""
        safety = git_safety
        
        snapshot = await safety.snapshot(run_tests=False)
        
        # Create uncommitted file
        dirty_file = temp_git_repo / "dirty.txt"
        dirty_file.write_text("dirty content")
        
        assert dirty_file.exists()
        
        # Rollback
        await safety.rollback(snapshot)
        
        # Uncommitted file should be gone
        assert not dirty_file.exists()
    
    async def test_rollback_to_commit_hash(self, git_safety, temp_git_repo):
        """Should rollback to raw commit hash."""
        safety = git_safety
        
        original_commit = await safety.get_current_commit()
        
        # Make change
        (temp_git_repo / "temp.txt").write_text("temp")
        await safety.commit("Temp commit")
        
        # Rollback using hash string
        await safety.rollback(original_commit)
        
        assert await safety.get_current_commit() == original_commit


@pytest.mark.asyncio
class TestGitSafetyMerge:
    """Merge operations."""
    
    async def test_merge_to_main_success(self, git_safety, temp_git_repo):
        """Should merge feature branch into main when tests pass."""
        safety = git_safety
        
        main_commit_before = await safety.get_current_commit()
        
        # Create feature branch
        await safety.create_branch("feature/test")
        (temp_git_repo / "feature.txt").write_text("feature")
        await safety.commit("Add feature")
        feature_commit = await safety.get_current_commit()
        
        # Merge back to main (tests pass with echo command)
        merge_commit = await safety.merge_to_main("feature/test", require_tests=False)
        
        # Should be on main with new merge commit
        assert await safety.get_current_branch() == "main"
        assert await safety.get_current_commit() == merge_commit
        assert merge_commit != main_commit_before
    
    async def test_merge_to_main_with_tests_failure(self, git_safety, temp_git_repo):
        """Should not merge when tests fail."""
        safety = GitSafety(
            repo_path=temp_git_repo,
            test_command="exit 1",  # Always fails
        )
        
        # Create feature branch
        await safety.create_branch("feature/failing")
        (temp_git_repo / "fail.txt").write_text("fail")
        await safety.commit("Add failing feature")
        
        # Merge should fail due to tests
        with pytest.raises(GitOperationError) as exc_info:
            await safety.merge_to_main("feature/failing", require_tests=True)
        
        assert "tests failed" in str(exc_info.value).lower() or "cannot merge" in str(exc_info.value).lower()


@pytest.mark.asyncio
class TestGitSafetyIntegration:
    """Full workflow integration tests."""
    
    async def test_full_self_edit_workflow(self, temp_git_repo):
        """Complete workflow: snapshot → branch → edit → commit → merge."""
        safety = GitSafety(
            repo_path=temp_git_repo,
            test_command="echo 'tests pass'",
        )
        
        # 1. Take snapshot
        snapshot = await safety.snapshot(run_tests=False)
        
        # 2. Create feature branch
        branch = await safety.create_branch("timmy/self-edit/test-feature")
        
        # 3. Make edits
        (temp_git_repo / "src" / "feature.py").parent.mkdir(parents=True, exist_ok=True)
        (temp_git_repo / "src" / "feature.py").write_text("""
def new_feature():
    return "Hello from new feature!"
""")
        
        # 4. Commit
        commit = await safety.commit("Add new feature", ["src/feature.py"])
        
        # 5. Merge to main
        merge_commit = await safety.merge_to_main(branch, require_tests=False)
        
        # Verify state
        assert await safety.get_current_branch() == "main"
        assert (temp_git_repo / "src" / "feature.py").exists()
        
    async def test_rollback_on_failure(self, temp_git_repo):
        """Rollback workflow when changes need to be abandoned."""
        safety = GitSafety(
            repo_path=temp_git_repo,
            test_command="echo 'tests pass'",
        )
        
        # Snapshot
        snapshot = await safety.snapshot(run_tests=False)
        original_commit = snapshot.commit_hash
        
        # Create branch and make changes
        await safety.create_branch("timmy/self-edit/bad-feature")
        (temp_git_repo / "bad.py").write_text("# Bad code")
        await safety.commit("Add bad feature")
        
        # Oops! Rollback
        await safety.rollback(snapshot)
        
        # Should be back to original state
        assert await safety.get_current_commit() == original_commit
        assert not (temp_git_repo / "bad.py").exists()
