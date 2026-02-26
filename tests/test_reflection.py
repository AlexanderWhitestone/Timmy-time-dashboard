"""Tests for Reflection Service.

Tests fallback and LLM-based reflection generation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from self_coding.modification_journal import ModificationAttempt, Outcome
from self_coding.reflection import ReflectionService


class MockLLMResponse:
    """Mock LLM response."""
    def __init__(self, content: str, provider_used: str = "mock"):
        self.content = content
        self.provider_used = provider_used
        self.latency_ms = 100.0
        self.fallback_used = False


@pytest.mark.asyncio
class TestReflectionServiceFallback:
    """Fallback reflections without LLM."""
    
    async def test_fallback_success(self):
        """Should generate fallback reflection for success."""
        service = ReflectionService(llm_adapter=None)
        
        attempt = ModificationAttempt(
            task_description="Add error handling",
            files_modified=["src/app.py"],
            outcome=Outcome.SUCCESS,
        )
        
        reflection = await service.reflect_on_attempt(attempt)
        
        assert "What went well" in reflection
        assert "successfully completed" in reflection.lower()
        assert "src/app.py" in reflection
    
    async def test_fallback_failure(self):
        """Should generate fallback reflection for failure."""
        service = ReflectionService(llm_adapter=None)
        
        attempt = ModificationAttempt(
            task_description="Refactor database",
            files_modified=["src/db.py", "src/models.py"],
            outcome=Outcome.FAILURE,
            failure_analysis="Circular dependency",
            retry_count=2,
        )
        
        reflection = await service.reflect_on_attempt(attempt)
        
        assert "What went well" in reflection
        assert "What could be improved" in reflection
        assert "circular dependency" in reflection.lower()
        assert "2 retries" in reflection
    
    async def test_fallback_rollback(self):
        """Should generate fallback reflection for rollback."""
        service = ReflectionService(llm_adapter=None)
        
        attempt = ModificationAttempt(
            task_description="Update API",
            files_modified=["src/api.py"],
            outcome=Outcome.ROLLBACK,
        )
        
        reflection = await service.reflect_on_attempt(attempt)
        
        assert "What went well" in reflection
        assert "rollback" in reflection.lower()
        assert "preferable to shipping broken code" in reflection.lower()


@pytest.mark.asyncio
class TestReflectionServiceWithLLM:
    """Reflections with mock LLM."""
    
    async def test_llm_reflection_success(self):
        """Should use LLM for reflection when available."""
        mock_adapter = AsyncMock()
        mock_adapter.chat.return_value = MockLLMResponse(
            "**What went well:** Clean implementation\n"
            "**What could be improved:** More tests\n"
            "**Next time:** Add edge cases\n"
            "**General lesson:** Always test errors"
        )
        
        service = ReflectionService(llm_adapter=mock_adapter)
        
        attempt = ModificationAttempt(
            task_description="Add validation",
            approach="Use Pydantic",
            files_modified=["src/validation.py"],
            outcome=Outcome.SUCCESS,
            test_results="5 passed",
        )
        
        reflection = await service.reflect_on_attempt(attempt)
        
        assert "Clean implementation" in reflection
        assert mock_adapter.chat.called
        
        # Check the prompt was formatted correctly
        call_args = mock_adapter.chat.call_args
        assert "Add validation" in call_args.kwargs["message"]
        assert "SUCCESS" in call_args.kwargs["message"]
    
    async def test_llm_reflection_failure_fallback(self):
        """Should fallback when LLM fails."""
        mock_adapter = AsyncMock()
        mock_adapter.chat.side_effect = Exception("LLM timeout")
        
        service = ReflectionService(llm_adapter=mock_adapter)
        
        attempt = ModificationAttempt(
            task_description="Fix bug",
            outcome=Outcome.FAILURE,
        )
        
        reflection = await service.reflect_on_attempt(attempt)
        
        # Should still return a reflection (fallback)
        assert "What went well" in reflection
        assert "What could be improved" in reflection


@pytest.mark.asyncio
class TestReflectionServiceWithContext:
    """Reflections with similar past attempts."""
    
    async def test_reflect_with_context(self):
        """Should include past attempts in reflection."""
        mock_adapter = AsyncMock()
        mock_adapter.chat.return_value = MockLLMResponse(
            "Reflection with historical context"
        )
        
        service = ReflectionService(llm_adapter=mock_adapter)
        
        current = ModificationAttempt(
            task_description="Add auth middleware",
            outcome=Outcome.SUCCESS,
        )
        
        past = ModificationAttempt(
            task_description="Add logging middleware",
            outcome=Outcome.SUCCESS,
            reflection="Good pattern: use decorators",
        )
        
        reflection = await service.reflect_with_context(current, [past])
        
        assert reflection == "Reflection with historical context"
        
        # Check context was included
        call_args = mock_adapter.chat.call_args
        assert "logging middleware" in call_args.kwargs["message"]
        assert "Good pattern: use decorators" in call_args.kwargs["message"]
    
    async def test_reflect_with_context_fallback(self):
        """Should fallback when LLM fails with context."""
        mock_adapter = AsyncMock()
        mock_adapter.chat.side_effect = Exception("LLM error")
        
        service = ReflectionService(llm_adapter=mock_adapter)
        
        current = ModificationAttempt(
            task_description="Add feature",
            outcome=Outcome.SUCCESS,
        )
        past = ModificationAttempt(
            task_description="Past feature",
            outcome=Outcome.SUCCESS,
            reflection="Past lesson",
        )
        
        # Should fallback to regular reflection
        reflection = await service.reflect_with_context(current, [past])
        
        assert "What went well" in reflection


@pytest.mark.asyncio
class TestReflectionServiceEdgeCases:
    """Edge cases and error handling."""
    
    async def test_empty_files_list(self):
        """Should handle empty files list."""
        service = ReflectionService(llm_adapter=None)
        
        attempt = ModificationAttempt(
            task_description="Test task",
            files_modified=[],
            outcome=Outcome.SUCCESS,
        )
        
        reflection = await service.reflect_on_attempt(attempt)
        
        assert "What went well" in reflection
        assert "N/A" in reflection or "these files" in reflection
    
    async def test_long_test_results_truncated(self):
        """Should truncate long test results in prompt."""
        mock_adapter = AsyncMock()
        mock_adapter.chat.return_value = MockLLMResponse("Short reflection")
        
        service = ReflectionService(llm_adapter=mock_adapter)
        
        attempt = ModificationAttempt(
            task_description="Big refactor",
            outcome=Outcome.FAILURE,
            test_results="Error\n" * 1000,  # Very long
        )
        
        await service.reflect_on_attempt(attempt)
        
        # Check that test results were truncated in the prompt
        call_args = mock_adapter.chat.call_args
        prompt = call_args.kwargs["message"]
        assert len(prompt) < 10000  # Should be truncated
    
    async def test_no_approach_documented(self):
        """Should handle missing approach."""
        service = ReflectionService(llm_adapter=None)
        
        attempt = ModificationAttempt(
            task_description="Quick fix",
            approach="",  # Empty
            outcome=Outcome.SUCCESS,
        )
        
        reflection = await service.reflect_on_attempt(attempt)
        
        assert "What went well" in reflection
        assert "No approach documented" not in reflection  # Should use fallback
