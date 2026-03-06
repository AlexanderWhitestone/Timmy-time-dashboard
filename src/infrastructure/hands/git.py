"""Git Hand — version-control operations for Timmy.

Provides git capabilities with:
- Safe defaults (no force-push without explicit override)
- Approval gates for destructive operations
- Structured result parsing
- Working-directory pinning to repo root

Follows project conventions:
- Config via ``from config import settings``
- Singleton pattern for module-level import
- Graceful degradation: log error, return fallback, never crash
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# Operations that require explicit confirmation before execution
DESTRUCTIVE_OPS = frozenset({
    "push --force",
    "push -f",
    "reset --hard",
    "clean -fd",
    "clean -f",
    "branch -D",
    "checkout -- .",
    "restore .",
})


@dataclass
class GitResult:
    """Result from a git operation."""

    operation: str
    success: bool
    output: str = ""
    error: str = ""
    latency_ms: float = 0.0
    requires_confirmation: bool = False
    metadata: dict = field(default_factory=dict)


class GitHand:
    """Git operations hand for Timmy.

    All methods degrade gracefully — if git is not available or the
    command fails, the hand returns a ``GitResult(success=False)``
    rather than raising.
    """

    def __init__(self, repo_dir: Optional[str] = None, timeout: int = 60) -> None:
        self._repo_dir = repo_dir or settings.repo_root or None
        self._timeout = timeout
        logger.info("GitHand initialised — repo=%s", self._repo_dir)

    def _is_destructive(self, args: str) -> bool:
        """Check if a git operation is destructive."""
        for op in DESTRUCTIVE_OPS:
            if op in args:
                return True
        return False

    async def run(
        self,
        args: str,
        timeout: Optional[int] = None,
        allow_destructive: bool = False,
    ) -> GitResult:
        """Execute a git command.

        Args:
            args: Git arguments (e.g. "status", "log --oneline -5").
            timeout: Override default timeout (seconds).
            allow_destructive: Must be True to run destructive ops.

        Returns:
            GitResult with output or error details.
        """
        start = time.time()

        # Gate destructive operations
        if self._is_destructive(args) and not allow_destructive:
            return GitResult(
                operation=f"git {args}",
                success=False,
                error=(
                    f"Destructive operation blocked: 'git {args}'. "
                    "Set allow_destructive=True to override."
                ),
                requires_confirmation=True,
                latency_ms=(time.time() - start) * 1000,
            )

        effective_timeout = timeout or self._timeout
        command = f"git {args}"

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args.split(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._repo_dir,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=effective_timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                latency = (time.time() - start) * 1000
                logger.warning("Git command timed out after %ds: %s", effective_timeout, command)
                return GitResult(
                    operation=command,
                    success=False,
                    error=f"Command timed out after {effective_timeout}s",
                    latency_ms=latency,
                )

            latency = (time.time() - start) * 1000
            exit_code = proc.returncode or 0
            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

            return GitResult(
                operation=command,
                success=exit_code == 0,
                output=stdout,
                error=stderr if exit_code != 0 else "",
                latency_ms=latency,
            )

        except FileNotFoundError:
            latency = (time.time() - start) * 1000
            logger.warning("git binary not found")
            return GitResult(
                operation=command,
                success=False,
                error="git binary not found on PATH",
                latency_ms=latency,
            )
        except Exception as exc:
            latency = (time.time() - start) * 1000
            logger.warning("Git command failed: %s — %s", command, exc)
            return GitResult(
                operation=command,
                success=False,
                error=str(exc),
                latency_ms=latency,
            )

    # ── Convenience wrappers ─────────────────────────────────────────────────

    async def status(self) -> GitResult:
        """Run ``git status --short``."""
        return await self.run("status --short")

    async def log(self, count: int = 10) -> GitResult:
        """Run ``git log --oneline``."""
        return await self.run(f"log --oneline -{count}")

    async def diff(self, staged: bool = False) -> GitResult:
        """Run ``git diff`` (or ``git diff --cached`` for staged)."""
        args = "diff --cached" if staged else "diff"
        return await self.run(args)

    async def add(self, paths: str = ".") -> GitResult:
        """Stage files."""
        return await self.run(f"add {paths}")

    async def commit(self, message: str) -> GitResult:
        """Create a commit with the given message."""
        # Use -- to prevent message from being interpreted as flags
        return await self.run(f"commit -m {message!r}")

    async def checkout_branch(self, branch: str, create: bool = False) -> GitResult:
        """Checkout (or create) a branch."""
        flag = "-b" if create else ""
        return await self.run(f"checkout {flag} {branch}".strip())

    async def push(self, remote: str = "origin", branch: str = "", force: bool = False) -> GitResult:
        """Push to remote. Force-push requires explicit opt-in."""
        args = f"push -u {remote} {branch}".strip()
        if force:
            args = f"push --force {remote} {branch}".strip()
            return await self.run(args, allow_destructive=True)
        return await self.run(args)

    async def clone(self, url: str, dest: str = "") -> GitResult:
        """Clone a repository."""
        args = f"clone {url}"
        if dest:
            args += f" {dest}"
        return await self.run(args, timeout=120)

    async def pull(self, remote: str = "origin", branch: str = "") -> GitResult:
        """Pull from remote."""
        args = f"pull {remote} {branch}".strip()
        return await self.run(args)

    def info(self) -> dict:
        """Return a status summary for the dashboard."""
        return {
            "repo_dir": self._repo_dir,
            "default_timeout": self._timeout,
        }


# ── Module-level singleton ──────────────────────────────────────────────────
git_hand = GitHand()
