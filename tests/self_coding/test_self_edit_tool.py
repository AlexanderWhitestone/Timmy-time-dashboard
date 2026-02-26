"""Tests for Self-Edit MCP Tool.

Tests the complete self-edit workflow with mocked dependencies.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from creative.tools.self_edit import (
    MAX_FILES_PER_COMMIT,
    MAX_RETRIES,
    PROTECTED_FILES,
    EditPlan,
    SelfEditResult,
    SelfEditTool,
    register_self_edit_tool,
    self_edit_tool,
)


@pytest.fixture
def temp_repo():
    """Create a temporary git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Initialize git
        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path, check=True, capture_output=True,
        )
        
        # Create src structure
        src_path = repo_path / "src" / "myproject"
        src_path.mkdir(parents=True)
        
        (src_path / "__init__.py").write_text("")
        (src_path / "app.py").write_text('''
"""Main application."""

def hello():
    return "Hello"
''')
        
        # Create tests
        tests_path = repo_path / "tests"
        tests_path.mkdir()
        (tests_path / "test_app.py").write_text('''
"""Tests for app."""
from myproject.app import hello

def test_hello():
    assert hello() == "Hello"
''')
        
        # Initial commit
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=repo_path, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=repo_path, check=True, capture_output=True,
        )
        
        yield repo_path


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings to enable self-modification."""
    with patch('creative.tools.self_edit.settings') as mock_settings:
        mock_settings.self_modify_enabled = True
        yield mock_settings


@pytest.fixture
def mock_llm():
    """Create mock LLM adapter."""
    mock = AsyncMock()
    mock.chat.return_value = MagicMock(
        content="""APPROACH: Add error handling
FILES_TO_MODIFY: src/myproject/app.py
FILES_TO_CREATE:
TESTS_TO_ADD: tests/test_app.py
EXPLANATION: Wrap function in try/except"""
    )
    return mock


@pytest.mark.asyncio
class TestSelfEditToolBasics:
    """Basic functionality tests."""
    
    async def test_initialization(self, temp_repo):
        """Should initialize with services."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        assert tool.repo_path == temp_repo
        assert tool.git is not None
        assert tool.indexer is not None
        assert tool.journal is not None
        assert tool.reflection is not None
    
    async def test_preflight_checks_clean_repo(self, temp_repo):
        """Should pass preflight on clean repo."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        assert await tool._preflight_checks() is True
    
    async def test_preflight_checks_dirty_repo(self, temp_repo):
        """Should fail preflight on dirty repo."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        # Make uncommitted change
        (temp_repo / "dirty.txt").write_text("dirty")
        
        assert await tool._preflight_checks() is False
    
    async def test_preflight_checks_wrong_branch(self, temp_repo):
        """Should fail preflight when not on main."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        # Create and checkout feature branch
        import subprocess
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_repo, check=True, capture_output=True,
        )
        
        assert await tool._preflight_checks() is False


@pytest.mark.asyncio
class TestSelfEditToolPlanning:
    """Edit planning tests."""
    
    async def test_plan_edit_with_llm(self, temp_repo, mock_llm):
        """Should generate plan using LLM."""
        tool = SelfEditTool(repo_path=temp_repo, llm_adapter=mock_llm)
        await tool._ensure_indexed()
        
        plan = await tool._plan_edit(
            task_description="Add error handling",
            relevant_files=["src/myproject/app.py"],
            similar_attempts=[],
        )
        
        assert isinstance(plan, EditPlan)
        assert plan.approach == "Add error handling"
        assert "src/myproject/app.py" in plan.files_to_modify
    
    async def test_plan_edit_without_llm(self, temp_repo):
        """Should generate fallback plan without LLM."""
        tool = SelfEditTool(repo_path=temp_repo, llm_adapter=None)
        await tool._ensure_indexed()
        
        plan = await tool._plan_edit(
            task_description="Add feature",
            relevant_files=["src/myproject/app.py"],
            similar_attempts=[],
        )
        
        assert isinstance(plan, EditPlan)
        assert len(plan.files_to_modify) > 0
    
    async def test_plan_respects_max_files(self, temp_repo, mock_llm):
        """Plan should respect MAX_FILES_PER_COMMIT."""
        tool = SelfEditTool(repo_path=temp_repo, llm_adapter=mock_llm)
        await tool._ensure_indexed()
        
        # Mock LLM to return many files
        mock_llm.chat.return_value = MagicMock(
            content="FILES_TO_MODIFY: " + ",".join([f"file{i}.py" for i in range(10)])
        )
        
        plan = await tool._plan_edit(
            task_description="Test",
            relevant_files=[f"file{i}.py" for i in range(10)],
            similar_attempts=[],
        )
        
        assert len(plan.files_to_modify) <= MAX_FILES_PER_COMMIT


@pytest.mark.asyncio
class TestSelfEditToolValidation:
    """Safety constraint validation tests."""
    
    async def test_validate_plan_too_many_files(self, temp_repo):
        """Should reject plan with too many files."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        plan = EditPlan(
            approach="Test",
            files_to_modify=[f"file{i}.py" for i in range(MAX_FILES_PER_COMMIT + 1)],
            files_to_create=[],
            tests_to_add=[],
            explanation="Test",
        )
        
        assert tool._validate_plan(plan) is False
    
    async def test_validate_plan_protected_file(self, temp_repo):
        """Should reject plan modifying protected files."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        plan = EditPlan(
            approach="Test",
            files_to_modify=["src/tools/self_edit.py"],
            files_to_create=[],
            tests_to_add=[],
            explanation="Test",
        )
        
        assert tool._validate_plan(plan) is False
    
    async def test_validate_plan_valid(self, temp_repo):
        """Should accept valid plan."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        plan = EditPlan(
            approach="Test",
            files_to_modify=["src/myproject/app.py"],
            files_to_create=[],
            tests_to_add=[],
            explanation="Test",
        )
        
        assert tool._validate_plan(plan) is True


@pytest.mark.asyncio
class TestSelfEditToolExecution:
    """Edit execution tests."""
    
    async def test_strip_code_fences(self, temp_repo):
        """Should strip markdown code fences."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        content = "```python\ndef test(): pass\n```"
        result = tool._strip_code_fences(content)
        
        assert "```" not in result
        assert "def test(): pass" in result
    
    async def test_parse_list(self, temp_repo):
        """Should parse comma-separated lists."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        assert tool._parse_list("a, b, c") == ["a", "b", "c"]
        assert tool._parse_list("none") == []
        assert tool._parse_list("") == []
        assert tool._parse_list("N/A") == []


@pytest.mark.asyncio
class TestSelfEditToolIntegration:
    """Integration tests with mocked dependencies."""
    
    async def test_successful_edit_flow(self, temp_repo, mock_llm):
        """Test complete successful edit flow."""
        tool = SelfEditTool(repo_path=temp_repo, llm_adapter=mock_llm)
        
        # Mock Aider to succeed
        with patch.object(tool, '_aider_available', return_value=False):
            with patch.object(tool, '_execute_direct_edit') as mock_exec:
                mock_exec.return_value = {
                    "success": True,
                    "test_output": "1 passed",
                }
                
                result = await tool.execute("Add error handling")
                
                assert result.success is True
                assert result.attempt_id is not None
    
    async def test_failed_edit_with_rollback(self, temp_repo, mock_llm):
        """Test failed edit with rollback."""
        tool = SelfEditTool(repo_path=temp_repo, llm_adapter=mock_llm)
        
        # Mock execution to always fail
        with patch.object(tool, '_execute_edit') as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "error": "Tests failed",
                "test_output": "1 failed",
            }
            
            result = await tool.execute("Add broken feature")
            
            assert result.success is False
            assert result.attempt_id is not None
            assert "failed" in result.message.lower() or "retry" in result.message.lower()
    
    async def test_preflight_failure(self, temp_repo):
        """Should fail early if preflight checks fail."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        # Make repo dirty
        (temp_repo / "dirty.txt").write_text("dirty")
        
        result = await tool.execute("Some task")
        
        assert result.success is False
        assert "pre-flight" in result.message.lower()


@pytest.mark.asyncio
class TestSelfEditMCPRegistration:
    """MCP tool registration tests."""
    
    async def test_register_self_edit_tool(self):
        """Should register with MCP registry."""
        mock_registry = MagicMock()
        mock_llm = AsyncMock()
        
        register_self_edit_tool(mock_registry, mock_llm)
        
        mock_registry.register.assert_called_once()
        call_args = mock_registry.register.call_args
        
        assert call_args.kwargs["name"] == "self_edit"
        assert call_args.kwargs["requires_confirmation"] is True
        assert "self_coding" in call_args.kwargs["category"]


@pytest.mark.asyncio
class TestSelfEditGlobalTool:
    """Global tool instance tests."""
    
    async def test_self_edit_tool_singleton(self, temp_repo):
        """Should use singleton pattern."""
        from creative.tools import self_edit as self_edit_module
        
        # Reset singleton
        self_edit_module._self_edit_tool = None
        
        # First call should initialize
        with patch.object(SelfEditTool, '__init__', return_value=None) as mock_init:
            mock_init.return_value = None
            
            with patch.object(SelfEditTool, 'execute') as mock_execute:
                mock_execute.return_value = SelfEditResult(
                    success=True,
                    message="Test",
                )
                
                await self_edit_tool("Test task")
                
                mock_init.assert_called_once()
                mock_execute.assert_called_once()


@pytest.mark.asyncio
class TestSelfEditErrorHandling:
    """Error handling tests."""
    
    async def test_exception_handling(self, temp_repo):
        """Should handle exceptions gracefully."""
        tool = SelfEditTool(repo_path=temp_repo)
        
        # Mock preflight to raise exception
        with patch.object(tool, '_preflight_checks', side_effect=Exception("Unexpected")):
            result = await tool.execute("Test task")
            
            assert result.success is False
            assert "exception" in result.message.lower()
    
    async def test_llm_failure_fallback(self, temp_repo, mock_llm):
        """Should fallback when LLM fails."""
        tool = SelfEditTool(repo_path=temp_repo, llm_adapter=mock_llm)
        await tool._ensure_indexed()
        
        # Mock LLM to fail
        mock_llm.chat.side_effect = Exception("LLM timeout")
        
        plan = await tool._plan_edit(
            task_description="Test",
            relevant_files=["src/app.py"],
            similar_attempts=[],
        )
        
        # Should return fallback plan
        assert isinstance(plan, EditPlan)
        assert len(plan.files_to_modify) > 0
