"""Git Safety Layer — Atomic git operations with rollback capability.

All self-modifications happen on feature branches. Only merge to main after
full test suite passes. Snapshots enable rollback on failure.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snapshot:
    """Immutable snapshot of repository state before modification.
    
    Attributes:
        commit_hash: Git commit hash at snapshot time
        branch: Current branch name
        timestamp: When snapshot was taken
        test_status: Whether tests were passing at snapshot time
        test_output: Pytest output from test run
        clean: Whether working directory was clean
    """
    commit_hash: str
    branch: str
    timestamp: datetime
    test_status: bool
    test_output: str
    clean: bool


class GitSafetyError(Exception):
    """Base exception for git safety operations."""
    pass


class GitNotRepositoryError(GitSafetyError):
    """Raised when operation is attempted outside a git repository."""
    pass


class GitDirtyWorkingDirectoryError(GitSafetyError):
    """Raised when working directory is not clean and clean_required=True."""
    pass


class GitOperationError(GitSafetyError):
    """Raised when a git operation fails."""
    pass


class GitSafety:
    """Safe git operations for self-modification workflows.
    
    All operations are atomic and support rollback. Self-modifications happen
    on feature branches named 'timmy/self-edit/{timestamp}'. Only merged to
    main after tests pass.
    
    Usage:
        safety = GitSafety(repo_path="/path/to/repo")
        
        # Take snapshot before changes
        snapshot = await safety.snapshot()
        
        # Create feature branch
        branch = await safety.create_branch(f"timmy/self-edit/{timestamp}")
        
        # Make changes, commit them
        await safety.commit("Add error handling", ["src/file.py"])
        
        # Run tests, merge if pass
        if tests_pass:
            await safety.merge_to_main(branch)
        else:
            await safety.rollback(snapshot)
    """
    
    def __init__(
        self,
        repo_path: Optional[str | Path] = None,
        main_branch: str = "main",
        test_command: str = "python -m pytest --tb=short -q",
    ) -> None:
        """Initialize GitSafety with repository path.
        
        Args:
            repo_path: Path to git repository. Defaults to current working directory.
            main_branch: Name of main branch (main, master, etc.)
            test_command: Command to run tests for snapshot validation
        """
        self.repo_path = Path(repo_path).resolve() if repo_path else Path.cwd()
        self.main_branch = main_branch
        self.test_command = test_command
        self._verify_git_repo()
        logger.info("GitSafety initialized for %s", self.repo_path)
    
    def _verify_git_repo(self) -> None:
        """Verify that repo_path is a git repository."""
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            raise GitNotRepositoryError(
                f"{self.repo_path} is not a git repository"
            )
    
    async def _run_git(
        self,
        *args: str,
        check: bool = True,
        capture_output: bool = True,
        timeout: float = 30.0,
    ) -> subprocess.CompletedProcess:
        """Run a git command asynchronously.
        
        Args:
            *args: Git command arguments
            check: Whether to raise on non-zero exit
            capture_output: Whether to capture stdout/stderr
            timeout: Maximum time to wait for command
            
        Returns:
            CompletedProcess with returncode, stdout, stderr
            
        Raises:
            GitOperationError: If git command fails and check=True
        """
        cmd = ["git", *args]
        logger.debug("Running: %s", " ".join(cmd))
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            
            result = subprocess.CompletedProcess(
                args=cmd,
                returncode=proc.returncode or 0,
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else "",
            )
            
            if check and result.returncode != 0:
                raise GitOperationError(
                    f"Git command failed: {' '.join(args)}\n"
                    f"stdout: {result.stdout}\nstderr: {result.stderr}"
                )
            
            return result
            
        except asyncio.TimeoutError as e:
            proc.kill()
            raise GitOperationError(f"Git command timed out after {timeout}s: {' '.join(args)}") from e
    
    async def _run_shell(
        self,
        command: str,
        timeout: float = 120.0,
    ) -> subprocess.CompletedProcess:
        """Run a shell command asynchronously.
        
        Args:
            command: Shell command to run
            timeout: Maximum time to wait
            
        Returns:
            CompletedProcess with returncode, stdout, stderr
        """
        logger.debug("Running shell: %s", command)
        
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=self.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
        
        return subprocess.CompletedProcess(
            args=command,
            returncode=proc.returncode or 0,
            stdout=stdout.decode(),
            stderr=stderr.decode(),
        )
    
    async def is_clean(self) -> bool:
        """Check if working directory is clean (no uncommitted changes).
        
        Returns:
            True if clean, False if there are uncommitted changes
        """
        result = await self._run_git("status", "--porcelain", check=False)
        return result.stdout.strip() == ""
    
    async def get_current_branch(self) -> str:
        """Get current git branch name.
        
        Returns:
            Current branch name
        """
        result = await self._run_git("branch", "--show-current")
        return result.stdout.strip()
    
    async def get_current_commit(self) -> str:
        """Get current commit hash.
        
        Returns:
            Full commit hash
        """
        result = await self._run_git("rev-parse", "HEAD")
        return result.stdout.strip()
    
    async def _run_tests(self) -> tuple[bool, str]:
        """Run test suite and return results.
        
        Returns:
            Tuple of (all_passed, test_output)
        """
        logger.info("Running tests: %s", self.test_command)
        result = await self._run_shell(self.test_command, timeout=300.0)
        passed = result.returncode == 0
        output = result.stdout + "\n" + result.stderr
        
        if passed:
            logger.info("Tests passed")
        else:
            logger.warning("Tests failed with returncode %d", result.returncode)
        
        return passed, output
    
    async def snapshot(self, run_tests: bool = True) -> Snapshot:
        """Take a snapshot of current repository state.
        
        Captures commit hash, branch, test status. Used for rollback if
        modifications fail.
        
        Args:
            run_tests: Whether to run tests as part of snapshot
            
        Returns:
            Snapshot object with current state
            
        Raises:
            GitOperationError: If git operations fail
        """
        logger.info("Taking snapshot of repository state")
        
        commit_hash = await self.get_current_commit()
        branch = await self.get_current_branch()
        clean = await self.is_clean()
        timestamp = datetime.now(timezone.utc)
        
        test_status = False
        test_output = ""
        
        if run_tests:
            test_status, test_output = await self._run_tests()
        else:
            test_status = True  # Assume OK if not running tests
            test_output = "Tests skipped"
        
        snapshot = Snapshot(
            commit_hash=commit_hash,
            branch=branch,
            timestamp=timestamp,
            test_status=test_status,
            test_output=test_output,
            clean=clean,
        )
        
        logger.info(
            "Snapshot taken: %s@%s (clean=%s, tests=%s)",
            branch,
            commit_hash[:8],
            clean,
            test_status,
        )
        
        return snapshot
    
    async def create_branch(self, name: str, base: Optional[str] = None) -> str:
        """Create and checkout a new feature branch.
        
        Args:
            name: Branch name (e.g., 'timmy/self-edit/20260226-143022')
            base: Base branch to create from (defaults to main_branch)
            
        Returns:
            Name of created branch
            
        Raises:
            GitOperationError: If branch creation fails
        """
        base = base or self.main_branch
        
        # Ensure we're on base branch and it's up to date
        await self._run_git("checkout", base)
        await self._run_git("pull", "origin", base, check=False)  # May fail if no remote
        
        # Create and checkout new branch
        await self._run_git("checkout", "-b", name)
        
        logger.info("Created branch %s from %s", name, base)
        return name
    
    async def commit(
        self,
        message: str,
        files: Optional[list[str | Path]] = None,
        allow_empty: bool = False,
    ) -> str:
        """Commit changes to current branch.
        
        Args:
            message: Commit message
            files: Specific files to commit (None = all changes)
            allow_empty: Whether to allow empty commits
            
        Returns:
            Commit hash of new commit
            
        Raises:
            GitOperationError: If commit fails
        """
        # Add files
        if files:
            for file_path in files:
                full_path = self.repo_path / file_path
                if not full_path.exists():
                    logger.warning("File does not exist: %s", file_path)
                await self._run_git("add", str(file_path))
        else:
            await self._run_git("add", "-A")
        
        # Check if there's anything to commit
        if not allow_empty:
            diff_result = await self._run_git(
                "diff", "--cached", "--quiet", check=False
            )
            if diff_result.returncode == 0:
                logger.warning("No changes to commit")
                return await self.get_current_commit()
        
        # Commit
        commit_args = ["commit", "-m", message]
        if allow_empty:
            commit_args.append("--allow-empty")
        
        await self._run_git(*commit_args)
        
        commit_hash = await self.get_current_commit()
        logger.info("Committed %s: %s", commit_hash[:8], message)
        
        return commit_hash
    
    async def get_diff(self, from_hash: str, to_hash: Optional[str] = None) -> str:
        """Get diff between commits.
        
        Args:
            from_hash: Starting commit hash (or Snapshot object hash)
            to_hash: Ending commit hash (None = current)
            
        Returns:
            Git diff as string
        """
        args = ["diff", from_hash]
        if to_hash:
            args.append(to_hash)
        
        result = await self._run_git(*args)
        return result.stdout
    
    async def rollback(self, snapshot: Snapshot | str) -> str:
        """Rollback to a previous snapshot.
        
        Hard resets to the snapshot commit and deletes any uncommitted changes.
        Use with caution — this is destructive.
        
        Args:
            snapshot: Snapshot object or commit hash to rollback to
            
        Returns:
            Commit hash after rollback
            
        Raises:
            GitOperationError: If rollback fails
        """
        if isinstance(snapshot, Snapshot):
            target_hash = snapshot.commit_hash
            target_branch = snapshot.branch
        else:
            target_hash = snapshot
            target_branch = None
        
        logger.warning("Rolling back to %s", target_hash[:8])
        
        # Reset to target commit
        await self._run_git("reset", "--hard", target_hash)
        
        # Clean any untracked files
        await self._run_git("clean", "-fd")
        
        # If we know the original branch, switch back to it
        if target_branch:
            branch_exists = await self._run_git(
                "branch", "--list", target_branch, check=False
            )
            if branch_exists.stdout.strip():
                await self._run_git("checkout", target_branch)
                logger.info("Switched back to branch %s", target_branch)
        
        current = await self.get_current_commit()
        logger.info("Rolled back to %s", current[:8])
        
        return current
    
    async def merge_to_main(
        self,
        branch: str,
        require_tests: bool = True,
    ) -> str:
        """Merge a feature branch into main after tests pass.
        
        Args:
            branch: Feature branch to merge
            require_tests: Whether to require tests to pass before merging
            
        Returns:
            Merge commit hash
            
        Raises:
            GitOperationError: If merge fails or tests don't pass
        """
        logger.info("Preparing to merge %s into %s", branch, self.main_branch)
        
        # Checkout the feature branch and run tests
        await self._run_git("checkout", branch)
        
        if require_tests:
            passed, output = await self._run_tests()
            if not passed:
                raise GitOperationError(
                    f"Cannot merge {branch}: tests failed\n{output}"
                )
        
        # Checkout main and merge
        await self._run_git("checkout", self.main_branch)
        await self._run_git("merge", "--no-ff", "-m", f"Merge {branch}", branch)
        
        # Optionally delete the feature branch
        await self._run_git("branch", "-d", branch, check=False)
        
        merge_hash = await self.get_current_commit()
        logger.info("Merged %s into %s: %s", branch, self.main_branch, merge_hash[:8])
        
        return merge_hash
    
    async def get_modified_files(self, since_hash: Optional[str] = None) -> list[str]:
        """Get list of files modified since a commit.
        
        Args:
            since_hash: Commit to compare against (None = uncommitted changes)
            
        Returns:
            List of modified file paths
        """
        if since_hash:
            result = await self._run_git(
                "diff", "--name-only", since_hash, "HEAD"
            )
        else:
            result = await self._run_git(
                "diff", "--name-only", "HEAD"
            )
        
        files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        return files
    
    async def stage_file(self, file_path: str | Path) -> None:
        """Stage a single file for commit.
        
        Args:
            file_path: Path to file relative to repo root
        """
        await self._run_git("add", str(file_path))
        logger.debug("Staged %s", file_path)
