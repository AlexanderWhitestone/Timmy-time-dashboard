"""Reflection Service — Generate lessons learned from modification attempts.

After every self-modification (success or failure), the Reflection Service
prompts an LLM to analyze the attempt and extract actionable insights.
"""

from __future__ import annotations

import logging
from typing import Optional

from self_coding.modification_journal import ModificationAttempt, Outcome

logger = logging.getLogger(__name__)


REFLECTION_SYSTEM_PROMPT = """You are a software engineering mentor analyzing a self-modification attempt.

Your goal is to provide constructive, specific feedback that helps improve future attempts.
Focus on patterns and principles rather than one-off issues.

Be concise but insightful. Maximum 300 words."""


REFLECTION_PROMPT_TEMPLATE = """A software agent just attempted to modify its own source code.

Task: {task_description}
Approach: {approach}
Files modified: {files_modified}
Outcome: {outcome}
Test results: {test_results}
{failure_section}

Reflect on this attempt:
1. What went well? (Be specific about techniques or strategies)
2. What could be improved? (Focus on process, not just the code)
3. What would you do differently next time?
4. What general lesson can be extracted for future similar tasks?

Provide your reflection in a structured format:

**What went well:**
[Your analysis]

**What could be improved:**
[Your analysis]

**Next time:**
[Specific actionable change]

**General lesson:**
[Extracted principle for similar tasks]"""


class ReflectionService:
    """Generates reflections on self-modification attempts.
    
    Uses an LLM to analyze attempts and extract lessons learned.
    Stores reflections in the Modification Journal for future reference.
    
    Usage:
        from self_coding.reflection import ReflectionService
        from timmy.cascade_adapter import TimmyCascadeAdapter
        
        adapter = TimmyCascadeAdapter()
        reflection_service = ReflectionService(llm_adapter=adapter)
        
        # After a modification attempt
        reflection_text = await reflection_service.reflect_on_attempt(attempt)
        
        # Store in journal
        await journal.update_reflection(attempt_id, reflection_text)
    """
    
    def __init__(
        self,
        llm_adapter: Optional[object] = None,
        model_preference: str = "fast",  # "fast" or "quality"
    ) -> None:
        """Initialize ReflectionService.
        
        Args:
            llm_adapter: LLM adapter (e.g., TimmyCascadeAdapter)
            model_preference: "fast" for quick reflections, "quality" for deeper analysis
        """
        self.llm_adapter = llm_adapter
        self.model_preference = model_preference
        logger.info("ReflectionService initialized")
    
    async def reflect_on_attempt(self, attempt: ModificationAttempt) -> str:
        """Generate a reflection on a modification attempt.
        
        Args:
            attempt: The modification attempt to reflect on
            
        Returns:
            Reflection text (structured markdown)
        """
        # Build the prompt
        failure_section = ""
        if attempt.outcome == Outcome.FAILURE and attempt.failure_analysis:
            failure_section = f"\nFailure analysis: {attempt.failure_analysis}"
        
        prompt = REFLECTION_PROMPT_TEMPLATE.format(
            task_description=attempt.task_description,
            approach=attempt.approach or "(No approach documented)",
            files_modified=", ".join(attempt.files_modified) if attempt.files_modified else "(No files modified)",
            outcome=attempt.outcome.value.upper(),
            test_results=attempt.test_results[:500] if attempt.test_results else "(No test results)",
            failure_section=failure_section,
        )
        
        # Call LLM if available
        if self.llm_adapter:
            try:
                response = await self.llm_adapter.chat(
                    message=prompt,
                    context=REFLECTION_SYSTEM_PROMPT,
                )
                reflection = response.content.strip()
                logger.info("Generated reflection for attempt (via %s)", 
                           response.provider_used)
                return reflection
            except Exception as e:
                logger.error("LLM reflection failed: %s", e)
                return self._generate_fallback_reflection(attempt)
        else:
            # No LLM available, use fallback
            return self._generate_fallback_reflection(attempt)
    
    def _generate_fallback_reflection(self, attempt: ModificationAttempt) -> str:
        """Generate a basic reflection without LLM.
        
        Used when no LLM adapter is available or LLM call fails.
        
        Args:
            attempt: The modification attempt
            
        Returns:
            Basic reflection text
        """
        if attempt.outcome == Outcome.SUCCESS:
            return f"""**What went well:**
Successfully completed: {attempt.task_description}
Files modified: {', '.join(attempt.files_modified) if attempt.files_modified else 'N/A'}

**What could be improved:**
Document the approach taken for future reference.

**Next time:**
Use the same pattern for similar tasks.

**General lesson:**
Modifications to {', '.join(attempt.files_modified) if attempt.files_modified else 'these files'} should include proper test coverage."""
        
        elif attempt.outcome == Outcome.FAILURE:
            return f"""**What went well:**
Attempted: {attempt.task_description}

**What could be improved:**
The modification failed after {attempt.retry_count} retries.
{attempt.failure_analysis if attempt.failure_analysis else 'Failure reason not documented.'}

**Next time:**
Consider breaking the task into smaller steps.
Validate approach with simpler test case first.

**General lesson:**
Changes affecting {', '.join(attempt.files_modified) if attempt.files_modified else 'multiple files'} require careful dependency analysis."""
        
        else:  # ROLLBACK
            return f"""**What went well:**
Recognized failure and rolled back to maintain stability.

**What could be improved:**
Early detection of issues before full implementation.

**Next time:**
Run tests more frequently during development.
Use smaller incremental commits.

**General lesson:**
Rollback is preferable to shipping broken code."""
    
    async def reflect_with_context(
        self,
        attempt: ModificationAttempt,
        similar_attempts: list[ModificationAttempt],
    ) -> str:
        """Generate reflection with context from similar past attempts.
        
        Includes relevant past reflections to build cumulative learning.
        
        Args:
            attempt: The current modification attempt
            similar_attempts: Similar past attempts (with reflections)
            
        Returns:
            Reflection text incorporating past learnings
        """
        # Build context from similar attempts
        context_parts = []
        for past in similar_attempts[:3]:  # Top 3 similar
            if past.reflection:
                context_parts.append(
                    f"Past similar task ({past.outcome.value}):\n"
                    f"Task: {past.task_description}\n"
                    f"Lesson: {past.reflection[:200]}..."
                )
        
        context = "\n\n".join(context_parts)
        
        # Build enhanced prompt
        failure_section = ""
        if attempt.outcome == Outcome.FAILURE and attempt.failure_analysis:
            failure_section = f"\nFailure analysis: {attempt.failure_analysis}"
        
        enhanced_prompt = f"""A software agent just attempted to modify its own source code.

Task: {attempt.task_description}
Approach: {attempt.approach or "(No approach documented)"}
Files modified: {', '.join(attempt.files_modified) if attempt.files_modified else "(No files modified)"}
Outcome: {attempt.outcome.value.upper()}
Test results: {attempt.test_results[:500] if attempt.test_results else "(No test results)"}
{failure_section}

---

Relevant past attempts:

{context if context else "(No similar past attempts)"}

---

Given this history, reflect on the current attempt:
1. What went well?
2. What could be improved?
3. How does this compare to past similar attempts?
4. What pattern or principle should guide future similar tasks?

Provide your reflection in a structured format:

**What went well:**
**What could be improved:**
**Comparison to past attempts:**
**Guiding principle:**"""
        
        if self.llm_adapter:
            try:
                response = await self.llm_adapter.chat(
                    message=enhanced_prompt,
                    context=REFLECTION_SYSTEM_PROMPT,
                )
                return response.content.strip()
            except Exception as e:
                logger.error("LLM reflection with context failed: %s", e)
                return await self.reflect_on_attempt(attempt)
        else:
            return await self.reflect_on_attempt(attempt)
