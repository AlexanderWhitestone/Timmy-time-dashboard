"""Self-modification loop — read source, generate edits, test, commit.

Orchestrates the full cycle for Timmy to modify its own codebase:
1. Create a working git branch
2. Read target source files
3. Send instruction + source to the LLM
4. Validate syntax before writing
5. Write edits to disk
6. Run pytest
7. On success -> git add + commit; on failure -> revert
8. On total failure -> diagnose from report, restart autonomously

Supports multiple LLM backends:
- "ollama"   — local Ollama (default, sovereign)
- "anthropic" — Claude API via Anthropic SDK
- "auto"     — try anthropic first (if key set), fall back to ollama

Reports are saved to data/self_modify_reports/ for debugging.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# Project root — two levels up from src/self_modify/
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Reports directory
REPORTS_DIR = PROJECT_ROOT / "data" / "self_modify_reports"

# Only one self-modification at a time
_LOCK = threading.Lock()

# Maximum file size we'll send to the LLM (bytes)
_MAX_FILE_SIZE = 50_000

# Delimiter format the LLM is instructed to use
_FILE_BLOCK_RE = re.compile(
    r"---\s*FILE:\s*(.+?)\s*---\n(.*?)---\s*END\s*FILE\s*---",
    re.DOTALL,
)

# Backend type literal
BACKENDS = ("ollama", "anthropic", "auto")


@dataclass
class ModifyRequest:
    """A request to modify code."""

    instruction: str
    target_files: list[str] = field(default_factory=list)
    dry_run: bool = False


@dataclass
class ModifyResult:
    """Result of a self-modification attempt."""

    success: bool
    files_changed: list[str] = field(default_factory=list)
    test_passed: bool = False
    commit_sha: Optional[str] = None
    branch_name: Optional[str] = None
    error: Optional[str] = None
    llm_response: str = ""
    attempts: int = 0
    report_path: Optional[str] = None
    autonomous_cycles: int = 0


class SelfModifyLoop:
    """Orchestrates the read -> edit -> test -> commit cycle.

    Supports autonomous self-correction: when all retries fail, reads its own
    failure report, diagnoses the root cause, and restarts with a corrected
    instruction.
    """

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        max_retries: Optional[int] = None,
        backend: Optional[str] = None,
        autonomous: bool = False,
        max_autonomous_cycles: int = 3,
    ) -> None:
        self._repo_path = repo_path or PROJECT_ROOT
        self._max_retries = (
            max_retries if max_retries is not None else settings.self_modify_max_retries
        )
        self._allowed_dirs = [
            d.strip() for d in settings.self_modify_allowed_dirs.split(",") if d.strip()
        ]
        self._run_id = f"{int(time.time())}"
        self._attempt_reports: list[dict] = []
        self._backend = backend or settings.self_modify_backend
        self._autonomous = autonomous
        self._max_autonomous_cycles = max_autonomous_cycles

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, request: ModifyRequest) -> ModifyResult:
        """Execute the full self-modification loop."""
        if not settings.self_modify_enabled:
            return ModifyResult(
                success=False,
                error="Self-modification is disabled. Set SELF_MODIFY_ENABLED=true.",
            )

        if not _LOCK.acquire(blocking=False):
            return ModifyResult(
                success=False,
                error="Another self-modification is already running.",
            )

        try:
            result = self._run_locked(request)
            report_path = self._save_report(request, result)
            result.report_path = str(report_path)

            # Autonomous mode: if failed, diagnose and restart
            if self._autonomous and not result.success and not request.dry_run:
                result = self._autonomous_loop(request, result, report_path)

            return result
        finally:
            _LOCK.release()

    # ── Autonomous self-correction ─────────────────────────────────────────

    def _autonomous_loop(
        self, original_request: ModifyRequest, last_result: ModifyResult, last_report: Path
    ) -> ModifyResult:
        """Read the failure report, diagnose, and restart with a fix."""
        for cycle in range(1, self._max_autonomous_cycles + 1):
            logger.info("Autonomous cycle %d/%d", cycle, self._max_autonomous_cycles)

            # Diagnose what went wrong
            diagnosis = self._diagnose_failure(last_report)
            if not diagnosis:
                logger.warning("Could not diagnose failure, stopping autonomous loop")
                last_result.autonomous_cycles = cycle
                return last_result

            logger.info("Diagnosis: %s", diagnosis[:200])

            # Build a corrected instruction
            corrected_instruction = (
                f"{original_request.instruction}\n\n"
                f"IMPORTANT CORRECTION from previous failure:\n{diagnosis}"
            )

            # Reset attempt reports for this cycle
            self._attempt_reports = []

            corrected_request = ModifyRequest(
                instruction=corrected_instruction,
                target_files=original_request.target_files,
                dry_run=original_request.dry_run,
            )

            result = self._run_locked(corrected_request)
            report_path = self._save_report(corrected_request, result)
            result.report_path = str(report_path)
            result.autonomous_cycles = cycle

            if result.success:
                logger.info("Autonomous cycle %d succeeded!", cycle)
                return result

            last_result = result
            last_report = report_path

        logger.warning("Autonomous loop exhausted after %d cycles", self._max_autonomous_cycles)
        return last_result

    def _diagnose_failure(self, report_path: Path) -> Optional[str]:
        """Read a failure report and produce a diagnosis + fix instruction.

        Uses the best available LLM to analyze the report. This is the
        'meta-reasoning' step — the agent reasoning about its own failures.
        """
        try:
            report_text = report_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error("Could not read report %s: %s", report_path, exc)
            return None

        # Truncate to keep within context limits
        if len(report_text) > 8000:
            report_text = report_text[:8000] + "\n... (truncated)"

        diagnosis_prompt = f"""You are a code debugging expert. Analyze this self-modification failure report and provide a concise diagnosis.

FAILURE REPORT:
{report_text}

Analyze the report and provide:
1. ROOT CAUSE: What specifically went wrong (syntax error, logic error, missing import, etc.)
2. FIX INSTRUCTIONS: Exact instructions for a code-generation LLM to avoid this mistake.
   Be very specific — e.g. "Do NOT start the file with triple-quotes" or
   "The em-dash character U+2014 must stay INSIDE a string literal, never outside one."

Keep your response under 500 words. Focus on actionable fix instructions."""

        try:
            raw = self._call_llm(diagnosis_prompt)
            return raw.strip() if raw else None
        except Exception as exc:
            logger.error("Diagnosis LLM call failed: %s", exc)
            return None

    # ── Internal orchestration ────────────────────────────────────────────────

    def _run_locked(self, request: ModifyRequest) -> ModifyResult:
        branch_name = None
        attempt = 0

        # Skip branch creation — writing files triggers container restarts
        # which kills the process mid-operation. Work on the current branch.
        if not os.environ.get("SELF_MODIFY_SKIP_BRANCH"):
            try:
                branch_name = self._create_branch()
            except Exception as exc:
                logger.warning("Could not create branch: %s (continuing on current)", exc)

        # Resolve target files
        target_files = request.target_files or self._infer_target_files(
            request.instruction
        )
        if not target_files:
            return ModifyResult(
                success=False,
                error="No target files identified. Specify target_files or use more specific language.",
                branch_name=branch_name,
            )

        # Validate paths
        try:
            self._validate_paths(target_files)
        except ValueError as exc:
            return ModifyResult(success=False, error=str(exc), branch_name=branch_name)

        last_test_output = ""
        last_llm_response = ""
        last_syntax_errors: dict[str, str] = {}

        while attempt <= self._max_retries:
            attempt += 1
            logger.info(
                "Self-modify attempt %d/%d: %s",
                attempt,
                self._max_retries + 1,
                request.instruction[:80],
            )

            # Read current contents
            file_contents = self._read_files(target_files)
            if not file_contents:
                return ModifyResult(
                    success=False,
                    error="Could not read any target files.",
                    branch_name=branch_name,
                    attempts=attempt,
                )

            # Generate edits via LLM
            try:
                edits, llm_response = self._generate_edits(
                    request.instruction, file_contents,
                    prev_test_output=last_test_output if attempt > 1 else None,
                    prev_syntax_errors=last_syntax_errors if attempt > 1 else None,
                )
                last_llm_response = llm_response
            except Exception as exc:
                self._attempt_reports.append({
                    "attempt": attempt,
                    "phase": "llm_generation",
                    "error": str(exc),
                })
                return ModifyResult(
                    success=False,
                    error=f"LLM generation failed: {exc}",
                    branch_name=branch_name,
                    attempts=attempt,
                )

            if not edits:
                self._attempt_reports.append({
                    "attempt": attempt,
                    "phase": "parse_edits",
                    "error": "No file edits parsed from LLM response",
                    "llm_response": llm_response,
                })
                return ModifyResult(
                    success=False,
                    error="LLM produced no file edits.",
                    llm_response=llm_response,
                    branch_name=branch_name,
                    attempts=attempt,
                )

            # Syntax validation — check BEFORE writing to disk
            syntax_errors = self._validate_syntax(edits)
            if syntax_errors:
                last_syntax_errors = syntax_errors
                error_summary = "; ".join(
                    f"{fp}: {err}" for fp, err in syntax_errors.items()
                )
                logger.warning("Syntax errors in LLM output: %s", error_summary)
                self._attempt_reports.append({
                    "attempt": attempt,
                    "phase": "syntax_validation",
                    "error": error_summary,
                    "edits_content": {fp: content for fp, content in edits.items()},
                    "llm_response": llm_response,
                })
                # Don't write — go straight to retry
                continue

            last_syntax_errors = {}

            if request.dry_run:
                self._attempt_reports.append({
                    "attempt": attempt,
                    "phase": "dry_run",
                    "edits": {fp: content[:500] + "..." if len(content) > 500 else content
                              for fp, content in edits.items()},
                    "llm_response": llm_response,
                })
                return ModifyResult(
                    success=True,
                    files_changed=list(edits.keys()),
                    llm_response=llm_response,
                    branch_name=branch_name,
                    attempts=attempt,
                )

            # Write edits
            written = self._write_files(edits)

            # Run tests
            test_passed, test_output = self._run_tests()
            last_test_output = test_output

            # Save per-attempt report
            self._attempt_reports.append({
                "attempt": attempt,
                "phase": "complete",
                "files_written": written,
                "edits_content": {fp: content for fp, content in edits.items()},
                "test_passed": test_passed,
                "test_output": test_output,
                "llm_response": llm_response,
            })

            if test_passed:
                sha = self._git_commit(
                    f"self-modify: {request.instruction[:72]}", written
                )
                return ModifyResult(
                    success=True,
                    files_changed=written,
                    test_passed=True,
                    commit_sha=sha,
                    branch_name=branch_name,
                    llm_response=llm_response,
                    attempts=attempt,
                )

            # Tests failed — revert and maybe retry
            logger.warning(
                "Tests failed on attempt %d: %s", attempt, test_output[:200]
            )
            self._revert_files(written)

        return ModifyResult(
            success=False,
            files_changed=[],
            test_passed=False,
            error=f"Tests failed after {attempt} attempt(s).",
            llm_response=last_llm_response,
            branch_name=branch_name,
            attempts=attempt,
        )

    # ── Syntax validation ──────────────────────────────────────────────────

    def _validate_syntax(self, edits: dict[str, str]) -> dict[str, str]:
        """Compile-check each .py file edit. Returns {path: error} for failures."""
        errors: dict[str, str] = {}
        for fp, content in edits.items():
            if not fp.endswith(".py"):
                continue
            try:
                compile(content, fp, "exec")
            except SyntaxError as exc:
                errors[fp] = f"line {exc.lineno}: {exc.msg}"
        return errors

    # ── Report saving ─────────────────────────────────────────────────────────

    def _save_report(self, request: ModifyRequest, result: ModifyResult) -> Path:
        """Save a detailed report to data/self_modify_reports/."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "_", request.instruction[:40].lower()).strip("_")
        report_file = REPORTS_DIR / f"{ts}_{slug}.md"

        lines = [
            f"# Self-Modify Report: {ts}",
            "",
            f"**Instruction:** {request.instruction[:200]}",
            f"**Target files:** {', '.join(request.target_files) or '(auto-detected)'}",
            f"**Dry run:** {request.dry_run}",
            f"**Backend:** {self._backend}",
            f"**Branch:** {result.branch_name or 'N/A'}",
            f"**Result:** {'SUCCESS' if result.success else 'FAILED'}",
            f"**Error:** {result.error or 'none'}",
            f"**Commit:** {result.commit_sha or 'none'}",
            f"**Attempts:** {result.attempts}",
            f"**Autonomous cycles:** {result.autonomous_cycles}",
            "",
        ]

        for attempt_data in self._attempt_reports:
            n = attempt_data.get("attempt", "?")
            phase = attempt_data.get("phase", "?")
            lines.append(f"## Attempt {n} -- {phase}")
            lines.append("")

            if "error" in attempt_data and attempt_data.get("phase") != "complete":
                lines.append(f"**Error:** {attempt_data['error']}")
                lines.append("")

            if "llm_response" in attempt_data:
                lines.append("### LLM Response")
                lines.append("```")
                lines.append(attempt_data["llm_response"])
                lines.append("```")
                lines.append("")

            if "edits_content" in attempt_data:
                lines.append("### Edits Written")
                for fp, content in attempt_data["edits_content"].items():
                    lines.append(f"#### {fp}")
                    lines.append("```python")
                    lines.append(content)
                    lines.append("```")
                    lines.append("")

            if "test_output" in attempt_data:
                lines.append(f"### Test Result: {'PASSED' if attempt_data.get('test_passed') else 'FAILED'}")
                lines.append("```")
                lines.append(attempt_data["test_output"])
                lines.append("```")
                lines.append("")

        report_text = "\n".join(lines)
        report_file.write_text(report_text, encoding="utf-8")
        logger.info("Report saved: %s", report_file)
        return report_file

    # ── Git helpers ───────────────────────────────────────────────────────────

    def _create_branch(self) -> str:
        """Create and switch to a working branch."""
        from tools.git_tools import git_branch

        branch_name = f"timmy/self-modify-{int(time.time())}"
        git_branch(self._repo_path, create=branch_name, switch=branch_name)
        logger.info("Created branch: %s", branch_name)
        return branch_name

    def _git_commit(self, message: str, files: list[str]) -> Optional[str]:
        """Stage files and commit."""
        from tools.git_tools import git_add, git_commit

        try:
            git_add(self._repo_path, paths=files)
            result = git_commit(self._repo_path, message)
            sha = result.get("sha")
            logger.info("Committed %s: %s", sha[:8] if sha else "?", message)
            return sha
        except Exception as exc:
            logger.error("Git commit failed: %s", exc)
            return None

    def _revert_files(self, file_paths: list[str]) -> None:
        """Restore files from git HEAD."""
        for fp in file_paths:
            try:
                subprocess.run(
                    ["git", "checkout", "HEAD", "--", fp],
                    cwd=self._repo_path,
                    capture_output=True,
                    timeout=10,
                )
            except Exception as exc:
                logger.error("Failed to revert %s: %s", fp, exc)

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _validate_paths(self, file_paths: list[str]) -> None:
        """Ensure all paths are within allowed directories."""
        for fp in file_paths:
            resolved = (self._repo_path / fp).resolve()
            repo_resolved = self._repo_path.resolve()
            if not str(resolved).startswith(str(repo_resolved)):
                raise ValueError(f"Path escapes repository: {fp}")
            rel = str(resolved.relative_to(repo_resolved))
            if not any(rel.startswith(d) for d in self._allowed_dirs):
                raise ValueError(
                    f"Path not in allowed directories ({self._allowed_dirs}): {fp}"
                )

    def _read_files(self, file_paths: list[str]) -> dict[str, str]:
        """Read file contents from disk."""
        contents: dict[str, str] = {}
        for fp in file_paths:
            full = self._repo_path / fp
            if not full.is_file():
                logger.warning("File not found: %s", full)
                continue
            if full.stat().st_size > _MAX_FILE_SIZE:
                logger.warning("File too large, skipping: %s", fp)
                continue
            try:
                contents[fp] = full.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Could not read %s: %s", fp, exc)
        return contents

    def _write_files(self, edits: dict[str, str]) -> list[str]:
        """Write edited content to disk. Returns paths written."""
        written: list[str] = []
        for fp, content in edits.items():
            full = self._repo_path / fp
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            written.append(fp)
            logger.info("Wrote %d bytes to %s", len(content), fp)
        return written

    def _infer_target_files(self, instruction: str) -> list[str]:
        """Guess which files to modify from the instruction text."""
        paths = re.findall(r"[\w/._-]+\.py", instruction)
        if paths:
            return paths

        keyword_files = {
            "config": ["src/config.py"],
            "health": ["src/dashboard/routes/health.py"],
            "swarm": ["src/swarm/coordinator.py"],
            "voice": ["src/voice/nlu.py"],
            "agent": ["src/timmy/agent.py"],
            "tool": ["src/timmy/tools.py"],
            "dashboard": ["src/dashboard/app.py"],
            "prompt": ["src/timmy/prompts.py"],
        }
        instruction_lower = instruction.lower()
        for keyword, files in keyword_files.items():
            if keyword in instruction_lower:
                return files
        return []

    # ── Test runner ───────────────────────────────────────────────────────────

    def _run_tests(self) -> tuple[bool, str]:
        """Run the test suite. Returns (passed, output)."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=self._repo_path,
                timeout=120,
            )
            output = (result.stdout + result.stderr).strip()
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "Tests timed out after 120s"
        except Exception as exc:
            return False, f"Failed to run tests: {exc}"

    # ── Multi-backend LLM ─────────────────────────────────────────────────────

    def _resolve_backend(self) -> str:
        """Resolve 'auto' backend to a concrete one."""
        if self._backend == "auto":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                return "anthropic"
            return "ollama"
        return self._backend

    def _call_llm(self, prompt: str) -> str:
        """Route a prompt to the configured LLM backend. Returns raw text."""
        backend = self._resolve_backend()

        if backend == "anthropic":
            return self._call_anthropic(prompt)
        else:
            return self._call_ollama(prompt)

    def _call_anthropic(self, prompt: str) -> str:
        """Call Claude via the Anthropic SDK."""
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set — cannot use anthropic backend")

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _call_ollama(self, prompt: str) -> str:
        """Call the local Ollama instance via Agno."""
        from agno.agent import Agent
        from agno.models.ollama import Ollama

        agent = Agent(
            name="SelfModify",
            model=Ollama(id=settings.ollama_model, host=settings.ollama_url),
            markdown=False,
        )
        run_result = agent.run(prompt, stream=False)
        return run_result.content if hasattr(run_result, "content") else str(run_result)

    # ── LLM interaction ───────────────────────────────────────────────────────

    def _generate_edits(
        self,
        instruction: str,
        file_contents: dict[str, str],
        prev_test_output: Optional[str] = None,
        prev_syntax_errors: Optional[dict[str, str]] = None,
    ) -> tuple[dict[str, str], str]:
        """Ask the LLM to generate file edits.

        Returns (edits_dict, raw_llm_response).
        """
        # Build the prompt
        files_block = ""
        for fp, content in file_contents.items():
            files_block += f"\n<FILE path=\"{fp}\">\n{content}\n</FILE>\n"

        retry_context = ""
        if prev_test_output:
            retry_context += f"""
PREVIOUS ATTEMPT FAILED with test errors:
<TEST_OUTPUT>
{prev_test_output[:2000]}
</TEST_OUTPUT>
Fix the issues shown above.
"""
        if prev_syntax_errors:
            errors_text = "\n".join(f"  {fp}: {err}" for fp, err in prev_syntax_errors.items())
            retry_context += f"""
PREVIOUS ATTEMPT HAD SYNTAX ERRORS (code was rejected before writing):
{errors_text}

You MUST produce syntactically valid Python. Run through the code mentally
and make sure all strings are properly terminated, all indentation is correct,
and there are no invalid characters outside of string literals.
"""

        prompt = f"""You are a precise code modification agent. Edit source files according to the instruction.

INSTRUCTION: {instruction}

CURRENT FILES:
{files_block}
{retry_context}
OUTPUT FORMAT — wrap each modified file like this:

<MODIFIED path="filepath">
complete file content here
</MODIFIED>

CRITICAL RULES:
- Output the COMPLETE file content, not just changed lines
- Keep ALL existing functionality unless told to remove it
- The output must be syntactically valid Python — verify mentally before outputting
- Preserve all special characters (unicode, em-dashes, etc.) exactly as they appear in the original
- Do NOT wrap the file content in triple-quotes or markdown code fences
- Do NOT start the file content with \"\"\" — that would turn the code into a string literal
- Follow the existing code style

Generate the modified files now:"""

        raw = self._call_llm(prompt)

        # Parse <MODIFIED path="..."> ... </MODIFIED> blocks
        edits = {}
        xml_re = re.compile(
            r'<MODIFIED\s+path=["\'](.+?)["\']\s*>\n?(.*?)</MODIFIED>',
            re.DOTALL,
        )
        for match in xml_re.finditer(raw):
            filepath = match.group(1).strip()
            content = match.group(2)
            # Strip trailing whitespace but keep a final newline
            content = content.rstrip() + "\n"
            edits[filepath] = content

        # Fallback: try the old delimiter format
        if not edits:
            for match in _FILE_BLOCK_RE.finditer(raw):
                filepath = match.group(1).strip()
                content = match.group(2).rstrip() + "\n"
                edits[filepath] = content

        # Last resort: single file + code block
        if not edits and len(file_contents) == 1:
            only_path = next(iter(file_contents))
            code_match = re.search(r"```(?:python)?\n(.*?)```", raw, re.DOTALL)
            if code_match:
                edits[only_path] = code_match.group(1).rstrip() + "\n"

        return edits, raw
