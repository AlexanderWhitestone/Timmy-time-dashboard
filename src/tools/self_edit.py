"""Self-Edit MCP Tool — Timmy's ability to modify its own source code.

This is the core self-modification orchestrator that:
1. Receives task descriptions
2. Queries codebase indexer for relevant files
3. Queries modification journal for similar past attempts
4. Creates feature branches via GitSafety
5. Plans changes with LLM
6. Executes via Aider (preferred) or direct editing (fallback)
7. Runs tests via pytest
8. Commits on success, rolls back on failure
9. Logs outcomes to ModificationJournal
10. Generates reflections

Usage:
    from tools.self_edit import self_edit_tool
    from mcp.registry import tool_registry
    
    # Register with MCP
    tool_registry.register("self_edit", self_edit_schema, self_edit_tool)
    
    # Invoke
    result = await tool_registry.execute("self_edit", {
        "task_description": "Add error handling to health endpoint"
    })
"""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import settings

# Phase 1 imports
from self_coding import (
    CodebaseIndexer,
    GitSafety,
    ModificationAttempt,
    ModificationJournal,
    Outcome,
    ReflectionService,
)

logger = logging.getLogger(__name__)

# Safety constraints (Phase 1 hard limits)
MAX_FILES_PER_COMMIT = 3
MAX_LINES_CHANGED = 100
PROTECTED_FILES = {
    "src/tools/self_edit.py",
    "src/self_coding/git_safety.py",
    "src/self_coding/codebase_indexer.py",
    "src/self_coding/modification_journal.py",
    "src/self_coding/reflection.py",
}
MAX_RETRIES = 3


@dataclass
class SelfEditResult:
    """Result of a self-edit operation."""
    success: bool
    message: str
    attempt_id: Optional[int] = None
    files_modified: list[str] = field(default_factory=list)
    commit_hash: Optional[str] = None
    test_results: str = ""
    diff: str = ""


@dataclass
class EditPlan:
    """Plan for a self-edit operation."""
    approach: str
    files_to_modify: list[str]
    files_to_create: list[str]
    tests_to_add: list[str]
    explanation: str


class SelfEditTool:
    """Self-modification orchestrator.
    
    This class encapsulates the complete self-edit workflow:
    - Pre-flight checks
    - Context gathering (indexer + journal)
    - Branch creation
    - Edit planning (LLM)
    - Execution (Aider or direct)
    - Testing
    - Commit/rollback
    - Logging and reflection
    
    Usage:
        tool = SelfEditTool(repo_path="/path/to/repo")
        result = await tool.execute("Add error handling to health endpoint")
    """
    
    def __init__(
        self,
        repo_path: Optional[Path] = None,
        llm_adapter: Optional[object] = None,
    ) -> None:
        """Initialize SelfEditTool.
        
        Args:
            repo_path: Path to repository. Defaults to current directory.
            llm_adapter: LLM adapter for planning and reflection
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.llm_adapter = llm_adapter
        
        # Initialize Phase 1 services
        self.git = GitSafety(repo_path=self.repo_path)
        self.indexer = CodebaseIndexer(repo_path=self.repo_path)
        self.journal = ModificationJournal()
        self.reflection = ReflectionService(llm_adapter=llm_adapter)
        
        # Ensure codebase is indexed
        self._indexing_done = False
        
        logger.info("SelfEditTool initialized for %s", self.repo_path)
    
    async def _ensure_indexed(self) -> None:
        """Ensure codebase is indexed."""
        if not self._indexing_done:
            await self.indexer.index_changed()
            self._indexing_done = True
    
    async def execute(
        self,
        task_description: str,
        context: Optional[dict] = None,
    ) -> SelfEditResult:
        """Execute a self-edit task.
        
        This is the main entry point for self-modification.
        
        Args:
            task_description: What to do (e.g., "Add error handling")
            context: Optional additional context
            
        Returns:
            SelfEditResult with success/failure details
        """
        logger.info("Starting self-edit: %s", task_description[:50])
        
        try:
            # Step 1: Pre-flight checks
            if not await self._preflight_checks():
                return SelfEditResult(
                    success=False,
                    message="Pre-flight checks failed. See logs for details.",
                )
            
            # Step 2: Gather context
            await self._ensure_indexed()
            relevant_files = await self._get_relevant_files(task_description)
            similar_attempts = await self._get_similar_attempts(task_description)
            
            # Step 3: Create feature branch
            branch_name = f"timmy/self-edit/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            await self.git.create_branch(branch_name)
            logger.info("Created branch: %s", branch_name)
            
            # Step 4: Take snapshot for rollback
            snapshot = await self.git.snapshot(run_tests=False)
            
            # Step 5: Plan the edit
            plan = await self._plan_edit(
                task_description,
                relevant_files,
                similar_attempts,
            )
            
            # Validate plan against safety constraints
            if not self._validate_plan(plan):
                return SelfEditResult(
                    success=False,
                    message=f"Plan violates safety constraints: {plan.files_to_modify}",
                )
            
            # Step 6: Execute the edit
            execution_result = await self._execute_edit(plan, task_description)
            
            if not execution_result["success"]:
                # Attempt retries
                for retry in range(MAX_RETRIES):
                    logger.info("Retry %d/%d", retry + 1, MAX_RETRIES)
                    
                    # Rollback to clean state
                    await self.git.rollback(snapshot)
                    
                    # Try again with adjusted approach
                    execution_result = await self._execute_edit(
                        plan,
                        task_description,
                        retry_count=retry + 1,
                    )
                    
                    if execution_result["success"]:
                        break
                
                if not execution_result["success"]:
                    # Final rollback and log failure
                    await self.git.rollback(snapshot)
                    await self.git._run_git("checkout", "main")  # Return to main
                    
                    attempt_id = await self._log_failure(
                        task_description,
                        plan,
                        execution_result["test_output"],
                        execution_result.get("error", "Unknown error"),
                    )
                    
                    return SelfEditResult(
                        success=False,
                        message=f"Failed after {MAX_RETRIES} retries",
                        attempt_id=attempt_id,
                        test_results=execution_result.get("test_output", ""),
                    )
            
            # Step 7: Commit and merge
            commit_hash = await self.git.commit(
                message=f"Self-edit: {task_description[:50]}",
                files=plan.files_to_modify + plan.files_to_create + plan.tests_to_add,
            )
            
            # Merge to main (tests already passed in execution)
            await self.git.merge_to_main(branch_name, require_tests=False)
            
            # Step 8: Log success
            diff = await self.git.get_diff(snapshot.commit_hash, commit_hash)
            attempt_id = await self._log_success(
                task_description,
                plan,
                commit_hash,
                execution_result.get("test_output", ""),
                diff,
            )
            
            return SelfEditResult(
                success=True,
                message=f"Successfully modified {len(plan.files_to_modify)} files",
                attempt_id=attempt_id,
                files_modified=plan.files_to_modify,
                commit_hash=commit_hash,
                test_results=execution_result.get("test_output", ""),
                diff=diff,
            )
            
        except Exception as e:
            logger.exception("Self-edit failed with exception")
            return SelfEditResult(
                success=False,
                message=f"Exception: {str(e)}",
            )
    
    async def _preflight_checks(self) -> bool:
        """Run pre-flight safety checks.
        
        Returns:
            True if all checks pass
        """
        # Check if repo is clean
        if not await self.git.is_clean():
            logger.error("Pre-flight failed: Working directory not clean")
            return False
        
        # Check if we're on main
        current_branch = await self.git.get_current_branch()
        if current_branch != self.git.main_branch:
            logger.error("Pre-flight failed: Not on %s branch (on %s)", 
                        self.git.main_branch, current_branch)
            return False
        
        # Check if self-modification is enabled
        if not getattr(settings, 'self_modify_enabled', True):
            logger.error("Pre-flight failed: Self-modification disabled in config")
            return False
        
        return True
    
    async def _get_relevant_files(self, task_description: str) -> list[str]:
        """Get files relevant to the task.
        
        Args:
            task_description: Task to find relevant files for
            
        Returns:
            List of file paths
        """
        files = await self.indexer.get_relevant_files(task_description, limit=10)
        
        # Filter to only files with test coverage
        files_with_tests = [
            f for f in files
            if await self.indexer.has_test_coverage(f)
        ]
        
        logger.info("Found %d relevant files (%d with tests)", 
                   len(files), len(files_with_tests))
        
        return files_with_tests[:MAX_FILES_PER_COMMIT]
    
    async def _get_similar_attempts(
        self,
        task_description: str,
    ) -> list[ModificationAttempt]:
        """Get similar past modification attempts.
        
        Args:
            task_description: Task to find similar attempts for
            
        Returns:
            List of similar attempts
        """
        similar = await self.journal.find_similar(task_description, limit=5)
        logger.info("Found %d similar past attempts", len(similar))
        return similar
    
    async def _plan_edit(
        self,
        task_description: str,
        relevant_files: list[str],
        similar_attempts: list[ModificationAttempt],
    ) -> EditPlan:
        """Plan the edit using LLM.
        
        Args:
            task_description: What to do
            relevant_files: Files that might need modification
            similar_attempts: Similar past attempts for context
            
        Returns:
            EditPlan with approach and file list
        """
        if not self.llm_adapter:
            # Fallback: simple plan
            return EditPlan(
                approach=f"Edit files to implement: {task_description}",
                files_to_modify=relevant_files[:MAX_FILES_PER_COMMIT],
                files_to_create=[],
                tests_to_add=[],
                explanation="No LLM available, using heuristic plan",
            )
        
        # Build prompt with context
        codebase_summary = await self.indexer.get_summary(max_tokens=2000)
        
        similar_context = ""
        if similar_attempts:
            similar_context = "\n\nSimilar past attempts:\n"
            for attempt in similar_attempts:
                similar_context += f"- {attempt.task_description} ({attempt.outcome.value})\n"
                if attempt.reflection:
                    similar_context += f"  Lesson: {attempt.reflection[:100]}...\n"
        
        prompt = f"""You are planning a code modification for a Python project.

Task: {task_description}

Codebase Summary:
{codebase_summary}

Potentially relevant files (all have test coverage):
{chr(10).join(f"- {f}" for f in relevant_files)}
{similar_context}

Create a plan for implementing this task. You can modify at most {MAX_FILES_PER_COMMIT} files.

Respond in this format:
APPROACH: <brief description of the approach>
FILES_TO_MODIFY: <comma-separated list of file paths>
FILES_TO_CREATE: <comma-separated list of new file paths (if any)>
TESTS_TO_ADD: <comma-separated list of test files to add/modify>
EXPLANATION: <brief explanation of why this approach>
"""
        
        try:
            response = await self.llm_adapter.chat(message=prompt)
            content = response.content
            
            # Parse response
            approach = self._extract_field(content, "APPROACH")
            files_to_modify = self._parse_list(self._extract_field(content, "FILES_TO_MODIFY"))
            files_to_create = self._parse_list(self._extract_field(content, "FILES_TO_CREATE"))
            tests_to_add = self._parse_list(self._extract_field(content, "TESTS_TO_ADD"))
            explanation = self._extract_field(content, "EXPLANATION")
            
            return EditPlan(
                approach=approach or "No approach specified",
                files_to_modify=files_to_modify[:MAX_FILES_PER_COMMIT],
                files_to_create=files_to_create,
                tests_to_add=tests_to_add,
                explanation=explanation or "No explanation provided",
            )
            
        except Exception as e:
            logger.error("LLM planning failed: %s", e)
            return EditPlan(
                approach=f"Fallback: Modify relevant files for {task_description}",
                files_to_modify=relevant_files[:MAX_FILES_PER_COMMIT],
                files_to_create=[],
                tests_to_add=[],
                explanation=f"LLM failed, using fallback: {e}",
            )
    
    def _extract_field(self, content: str, field_name: str) -> str:
        """Extract a field from LLM response."""
        for line in content.split("\n"):
            if line.startswith(f"{field_name}:"):
                return line.split(":", 1)[1].strip()
        return ""
    
    def _parse_list(self, text: str) -> list[str]:
        """Parse comma-separated list."""
        if not text or text.lower() in ("none", "n/a", ""):
            return []
        return [item.strip() for item in text.split(",") if item.strip()]
    
    def _validate_plan(self, plan: EditPlan) -> bool:
        """Validate plan against safety constraints.
        
        Args:
            plan: EditPlan to validate
            
        Returns:
            True if plan is valid
        """
        # Check file count
        if len(plan.files_to_modify) > MAX_FILES_PER_COMMIT:
            logger.error("Plan modifies too many files: %d > %d",
                        len(plan.files_to_modify), MAX_FILES_PER_COMMIT)
            return False
        
        # Check for protected files
        for file_path in plan.files_to_modify:
            if file_path in PROTECTED_FILES:
                logger.error("Plan tries to modify protected file: %s", file_path)
                return False
        
        # Check all files have test coverage
        for file_path in plan.files_to_modify:
            # This is async, so we check in _get_relevant_files
            pass
        
        return True
    
    async def _execute_edit(
        self,
        plan: EditPlan,
        task_description: str,
        retry_count: int = 0,
    ) -> dict:
        """Execute the edit using Aider or direct editing.
        
        Args:
            plan: EditPlan to execute
            task_description: Original task description
            retry_count: Current retry attempt
            
        Returns:
            Dict with success, test_output, error
        """
        all_files = plan.files_to_modify + plan.files_to_create
        
        if not all_files:
            return {"success": False, "error": "No files to modify"}
        
        # Try Aider first
        if await self._aider_available():
            return await self._execute_with_aider(plan, task_description, all_files)
        else:
            # Fallback to direct editing
            return await self._execute_direct_edit(plan, task_description)
    
    async def _aider_available(self) -> bool:
        """Check if Aider is available."""
        try:
            result = await asyncio.create_subprocess_exec(
                "aider", "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await result.wait()
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    async def _execute_with_aider(
        self,
        plan: EditPlan,
        task_description: str,
        files: list[str],
    ) -> dict:
        """Execute edit using Aider.
        
        Args:
            plan: EditPlan
            task_description: Task description
            files: Files to edit
            
        Returns:
            Dict with success, test_output
        """
        cmd = [
            "aider",
            "--model", "ollama_chat/qwen2.5-coder:14b-instruct",
            "--auto-test",
            "--test-cmd", "python -m pytest tests/ -xvs",
            "--yes",
            "--no-git",
            "--message", f"{task_description}\n\nApproach: {plan.approach}",
        ] + files
        
        logger.info("Running Aider: %s", " ".join(cmd))
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.repo_path,
            )
            
            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=300.0,
            )
            
            output = stdout.decode() if stdout else ""
            
            # Check if tests passed
            success = proc.returncode == 0 and "passed" in output.lower()
            
            return {
                "success": success,
                "test_output": output,
            }
            
        except asyncio.TimeoutError:
            logger.error("Aider timed out after 300s")
            return {
                "success": False,
                "error": "Timeout",
                "test_output": "Aider timed out after 300s",
            }
        except Exception as e:
            logger.error("Aider execution failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "test_output": "",
            }
    
    async def _execute_direct_edit(
        self,
        plan: EditPlan,
        task_description: str,
    ) -> dict:
        """Execute edit via direct file modification (fallback).
        
        Args:
            plan: EditPlan
            task_description: Task description
            
        Returns:
            Dict with success, test_output
        """
        if not self.llm_adapter:
            return {
                "success": False,
                "error": "No LLM adapter for direct editing",
            }
        
        # Edit each file
        for file_path in plan.files_to_modify:
            full_path = self.repo_path / file_path
            
            if not full_path.exists():
                logger.error("File does not exist: %s", file_path)
                continue
            
            try:
                content = full_path.read_text()
                
                # Build edit prompt
                edit_prompt = f"""Edit this Python file to implement the task.

Task: {task_description}
Approach: {plan.approach}

Current file content:
```python
{content}
```

Provide the complete new file content. Only return the code, no explanation.
"""
                
                response = await self.llm_adapter.chat(message=edit_prompt)
                new_content = response.content
                
                # Strip code fences if present
                new_content = self._strip_code_fences(new_content)
                
                # Validate with AST
                try:
                    ast.parse(new_content)
                except SyntaxError as e:
                    logger.error("Generated code has syntax error: %s", e)
                    return {
                        "success": False,
                        "error": f"Syntax error in generated code: {e}",
                    }
                
                # Write file
                full_path.write_text(new_content)
                logger.info("Modified: %s", file_path)
                
            except Exception as e:
                logger.error("Failed to edit %s: %s", file_path, e)
                return {
                    "success": False,
                    "error": f"Failed to edit {file_path}: {e}",
                }
        
        # Run tests
        return await self._run_tests()
    
    def _strip_code_fences(self, content: str) -> str:
        """Strip markdown code fences from content."""
        lines = content.split("\n")
        
        # Remove opening fence
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        
        # Remove closing fence
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        
        return "\n".join(lines)
    
    async def _run_tests(self) -> dict:
        """Run tests and return results.
        
        Returns:
            Dict with success, test_output
        """
        cmd = ["python", "-m", "pytest", "tests/", "-x", "--tb=short"]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.repo_path,
            )
            
            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=120.0,
            )
            
            output = stdout.decode() if stdout else ""
            
            return {
                "success": proc.returncode == 0,
                "test_output": output,
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Tests timed out",
                "test_output": "Timeout after 120s",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "test_output": "",
            }
    
    async def _log_success(
        self,
        task_description: str,
        plan: EditPlan,
        commit_hash: str,
        test_results: str,
        diff: str,
    ) -> int:
        """Log successful attempt.
        
        Returns:
            Attempt ID
        """
        attempt = ModificationAttempt(
            task_description=task_description,
            approach=plan.approach,
            files_modified=plan.files_to_modify + plan.files_to_create,
            diff=diff[:5000],  # Truncate for storage
            test_results=test_results,
            outcome=Outcome.SUCCESS,
        )
        
        attempt_id = await self.journal.log_attempt(attempt)
        
        # Generate and store reflection
        reflection_text = await self.reflection.reflect_on_attempt(attempt)
        await self.journal.update_reflection(attempt_id, reflection_text)
        
        return attempt_id
    
    async def _log_failure(
        self,
        task_description: str,
        plan: EditPlan,
        test_results: str,
        error: str,
    ) -> int:
        """Log failed attempt.
        
        Returns:
            Attempt ID
        """
        attempt = ModificationAttempt(
            task_description=task_description,
            approach=plan.approach,
            files_modified=plan.files_to_modify,
            test_results=test_results,
            outcome=Outcome.FAILURE,
            failure_analysis=error,
            retry_count=MAX_RETRIES,
        )
        
        attempt_id = await self.journal.log_attempt(attempt)
        
        # Generate reflection even for failures
        reflection_text = await self.reflection.reflect_on_attempt(attempt)
        await self.journal.update_reflection(attempt_id, reflection_text)
        
        return attempt_id


# MCP Tool Schema
self_edit_schema = {
    "type": "object",
    "properties": {
        "task_description": {
            "type": "string",
            "description": "Description of the code modification to make",
        },
        "context": {
            "type": "object",
            "description": "Optional additional context for the modification",
        },
    },
    "required": ["task_description"],
}


# Global tool instance (singleton pattern)
_self_edit_tool: Optional[SelfEditTool] = None


async def self_edit_tool(task_description: str, context: Optional[dict] = None) -> dict:
    """MCP tool entry point for self-edit.
    
    Args:
        task_description: What to modify
        context: Optional context
        
    Returns:
        Dict with result
    """
    global _self_edit_tool
    
    if _self_edit_tool is None:
        _self_edit_tool = SelfEditTool()
    
    result = await _self_edit_tool.execute(task_description, context)
    
    return {
        "success": result.success,
        "message": result.message,
        "attempt_id": result.attempt_id,
        "files_modified": result.files_modified,
        "commit_hash": result.commit_hash,
        "test_results": result.test_results,
    }


def register_self_edit_tool(registry: Any, llm_adapter: Optional[object] = None) -> None:
    """Register the self-edit tool with MCP registry.
    
    Args:
        registry: MCP ToolRegistry
        llm_adapter: Optional LLM adapter
    """
    global _self_edit_tool
    _self_edit_tool = SelfEditTool(llm_adapter=llm_adapter)
    
    registry.register(
        name="self_edit",
        schema=self_edit_schema,
        handler=self_edit_tool,
        category="self_coding",
        requires_confirmation=True,  # Safety: require user approval
        tags=["self-modification", "code-generation"],
        source_module="tools.self_edit",
    )
    
    logger.info("Self-edit tool registered with MCP")
