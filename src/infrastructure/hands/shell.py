"""Shell Execution Hand — sandboxed command runner for Timmy.

Provides a restricted shell execution environment with:
- Configurable command allow-list
- Timeout enforcement
- Working-directory pinning
- Graceful degradation (never crashes the coordinator)

Follows project conventions:
- Config via ``from config import settings``
- Singleton pattern for module-level import
- Graceful degradation: log error, return fallback, never crash
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import time
from dataclasses import dataclass, field
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# Commands that are always blocked regardless of allow-list
_BLOCKED_COMMANDS = frozenset({
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero",
    ":(){ :|:& };:",  # fork bomb
    "> /dev/sda",
    "chmod -R 777 /",
})

# Default allow-list: safe build/dev commands
DEFAULT_ALLOWED_PREFIXES = (
    "make",
    "pytest",
    "python",
    "pip",
    "git",
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "echo",
    "env",
    "which",
    "uname",
    "whoami",
    "date",
    "wc",
    "sort",
    "uniq",
    "diff",
    "curl",
    "wget",
    "docker",
    "npm",
    "node",
    "cargo",
    "rustc",
)


@dataclass
class ShellResult:
    """Result from a shell command execution."""

    command: str
    success: bool
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    latency_ms: float = 0.0
    timed_out: bool = False
    metadata: dict = field(default_factory=dict)


class ShellHand:
    """Sandboxed shell executor for Timmy.

    All methods degrade gracefully — if a command fails or times out,
    the hand returns a ``ShellResult(success=False)`` rather than raising.
    """

    def __init__(
        self,
        allowed_prefixes: Optional[tuple[str, ...]] = None,
        default_timeout: int = 60,
        working_dir: Optional[str] = None,
    ) -> None:
        self._allowed_prefixes = allowed_prefixes or DEFAULT_ALLOWED_PREFIXES
        self._default_timeout = default_timeout
        self._working_dir = working_dir or settings.repo_root or None
        self._enabled = True
        logger.info(
            "ShellHand initialised — cwd=%s, timeout=%ds, %d allowed prefixes",
            self._working_dir,
            self._default_timeout,
            len(self._allowed_prefixes),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _validate_command(self, command: str) -> Optional[str]:
        """Validate a command against the allow-list.

        Returns None if valid, or an error message if blocked.
        """
        stripped = command.strip()

        # Check explicit block-list
        for blocked in _BLOCKED_COMMANDS:
            if blocked in stripped:
                return f"Command blocked by safety filter: {blocked!r}"

        # Check allow-list by first token
        try:
            tokens = shlex.split(stripped)
        except ValueError:
            tokens = stripped.split()

        if not tokens:
            return "Empty command"

        base_cmd = tokens[0].split("/")[-1]  # strip path prefix

        if base_cmd not in self._allowed_prefixes:
            return (
                f"Command '{base_cmd}' not in allow-list. "
                f"Allowed: {', '.join(sorted(self._allowed_prefixes))}"
            )

        return None

    async def run(
        self,
        command: str,
        timeout: Optional[int] = None,
        working_dir: Optional[str] = None,
        env: Optional[dict] = None,
    ) -> ShellResult:
        """Execute a shell command in a sandboxed environment.

        Args:
            command: The shell command to execute.
            timeout: Override default timeout (seconds).
            working_dir: Override default working directory.
            env: Additional environment variables to set.

        Returns:
            ShellResult with stdout/stderr or error details.
        """
        start = time.time()

        # Validate
        validation_error = self._validate_command(command)
        if validation_error:
            return ShellResult(
                command=command,
                success=False,
                error=validation_error,
                latency_ms=(time.time() - start) * 1000,
            )

        effective_timeout = timeout or self._default_timeout
        cwd = working_dir or self._working_dir

        try:
            import os

            run_env = os.environ.copy()
            if env:
                run_env.update(env)

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=run_env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=effective_timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                latency = (time.time() - start) * 1000
                logger.warning(
                    "Shell command timed out after %ds: %s", effective_timeout, command
                )
                return ShellResult(
                    command=command,
                    success=False,
                    exit_code=-1,
                    error=f"Command timed out after {effective_timeout}s",
                    latency_ms=latency,
                    timed_out=True,
                )

            latency = (time.time() - start) * 1000
            exit_code = proc.returncode or 0
            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

            return ShellResult(
                command=command,
                success=exit_code == 0,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                latency_ms=latency,
            )

        except Exception as exc:
            latency = (time.time() - start) * 1000
            logger.warning("Shell command failed: %s — %s", command, exc)
            return ShellResult(
                command=command,
                success=False,
                error=str(exc),
                latency_ms=latency,
            )

    def status(self) -> dict:
        """Return a status summary for the dashboard."""
        return {
            "enabled": self._enabled,
            "working_dir": self._working_dir,
            "default_timeout": self._default_timeout,
            "allowed_prefixes": list(self._allowed_prefixes),
        }


# ── Module-level singleton ──────────────────────────────────────────────────
shell_hand = ShellHand()
