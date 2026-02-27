"""Error path tests for Git Safety Layer.

Tests timeout handling, git failures, merge conflicts, and edge cases.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from self_coding.git_safety import (
    GitNotRepositoryError,
    GitOperationError,
    GitSafety,
)


@pytest.mark.asyncio
class TestGitSafetyErrors:
    """Git operation error handling."""
    
    async def test_invalid_repo_path(self):
        """Should raise GitNotRepositoryError for non-repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(GitNotRepositoryError):
                GitSafety(repo_path=tmpdir)
    
    async def test_git_command_failure(self):
        """Should raise GitOperationError on git failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True, capture_output=True)
            
            safety = GitSafety(repo_path=repo_path)
            
            # Try to checkout non-existent branch
            with pytest.raises(GitOperationError):
                await safety._run_git("checkout", "nonexistent-branch")
    
    async def test_merge_conflict_detection(self):
        """Should handle merge conflicts gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True, capture_output=True)
            
            # Create initial file
            (repo_path / "file.txt").write_text("original")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=repo_path, check=True, capture_output=True)
            
            safety = GitSafety(repo_path=repo_path)
            
            # Create branch A with changes
            await safety.create_branch("branch-a")
            (repo_path / "file.txt").write_text("branch-a changes")
            await safety.commit("Branch A changes")
            
            # Go back to main, create branch B with conflicting changes
            await safety._run_git("checkout", "main")
            await safety.create_branch("branch-b")
            (repo_path / "file.txt").write_text("branch-b changes")
            await safety.commit("Branch B changes")
            
            # Try to merge branch-a into branch-b (will conflict)
            with pytest.raises(GitOperationError):
                await safety._run_git("merge", "branch-a")
    
    async def test_rollback_after_merge(self):
        """Should be able to rollback even after merge."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True, capture_output=True)
            
            safety = GitSafety(repo_path=repo_path)
            
            # Initial commit
            (repo_path / "file.txt").write_text("v1")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "v1"], cwd=repo_path, check=True, capture_output=True)
            
            snapshot = await safety.snapshot(run_tests=False)
            
            # Make changes and commit
            (repo_path / "file.txt").write_text("v2")
            await safety.commit("v2")
            
            # Rollback
            await safety.rollback(snapshot)
            
            # Verify
            content = (repo_path / "file.txt").read_text()
            assert content == "v1"
    
    async def test_snapshot_with_failing_tests(self):
        """Snapshot should capture failing test status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True, capture_output=True)
            
            # Need an initial commit for HEAD to exist
            (repo_path / "initial.txt").write_text("initial")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
            
            # Create failing test
            (repo_path / "test_fail.py").write_text("def test_fail(): assert False")
            
            safety = GitSafety(
                repo_path=repo_path,
                test_command=f"{sys.executable} -m pytest test_fail.py -v",
            )
            
            snapshot = await safety.snapshot(run_tests=True)
            
            assert snapshot.test_status is False
            assert "FAILED" in snapshot.test_output or "failed" in snapshot.test_output.lower()
    
    async def test_get_diff_between_commits(self):
        """Should get diff between any two commits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True, capture_output=True)
            
            safety = GitSafety(repo_path=repo_path)
            
            # Commit 1
            (repo_path / "file.txt").write_text("version 1")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "v1"], cwd=repo_path, check=True, capture_output=True)
            commit1 = await safety.get_current_commit()
            
            # Commit 2
            (repo_path / "file.txt").write_text("version 2")
            await safety.commit("v2")
            commit2 = await safety.get_current_commit()
            
            # Get diff
            diff = await safety.get_diff(commit1, commit2)
            
            assert "version 1" in diff
            assert "version 2" in diff
    
    async def test_is_clean_with_untracked_files(self):
        """is_clean should return False with untracked files (they count as changes)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True, capture_output=True)
            
            # Need an initial commit for HEAD to exist
            (repo_path / "initial.txt").write_text("initial")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
            
            safety = GitSafety(repo_path=repo_path)
            
            # Verify clean state first
            assert await safety.is_clean() is True
            
            # Create untracked file
            (repo_path / "untracked.txt").write_text("untracked")
            
            # is_clean returns False when there are untracked files
            # (git status --porcelain shows ?? for untracked)
            assert await safety.is_clean() is False
    
    async def test_empty_commit_allowed(self):
        """Should allow empty commits when requested."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True, capture_output=True)
            
            # Initial commit
            (repo_path / "file.txt").write_text("content")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
            
            safety = GitSafety(repo_path=repo_path)
            
            # Empty commit
            commit_hash = await safety.commit("Empty commit message", allow_empty=True)
            
            assert len(commit_hash) == 40
    
    async def test_modified_files_detection(self):
        """Should detect which files were modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True, capture_output=True)
            
            safety = GitSafety(repo_path=repo_path)
            
            # Initial commits
            (repo_path / "file1.txt").write_text("content1")
            (repo_path / "file2.txt").write_text("content2")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
            
            base_commit = await safety.get_current_commit()
            
            # Modify only file1
            (repo_path / "file1.txt").write_text("modified content")
            await safety.commit("Modify file1")
            
            # Get modified files
            modified = await safety.get_modified_files(base_commit)
            
            assert "file1.txt" in modified
            assert "file2.txt" not in modified
    
    async def test_branch_switching(self):
        """Should handle switching between branches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True, capture_output=True)
            
            # Initial commit on master (default branch name)
            (repo_path / "main.txt").write_text("main branch content")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
            # Rename to main for consistency
            subprocess.run(["git", "branch", "-M", "main"], cwd=repo_path, check=True, capture_output=True)
            
            safety = GitSafety(repo_path=repo_path, main_branch="main")
            
            # Create feature branch
            await safety.create_branch("feature")
            (repo_path / "feature.txt").write_text("feature content")
            await safety.commit("Add feature")
            
            # Switch back to main
            await safety._run_git("checkout", "main")
            
            # Verify main doesn't have feature.txt
            assert not (repo_path / "feature.txt").exists()
            
            # Switch to feature
            await safety._run_git("checkout", "feature")
            
            # Verify feature has feature.txt
            assert (repo_path / "feature.txt").exists()
