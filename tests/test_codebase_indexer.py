"""Tests for Codebase Indexer.

Uses temporary directories with Python files to test AST parsing and indexing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from self_coding.codebase_indexer import CodebaseIndexer, ModuleInfo


@pytest.fixture
def temp_repo():
    """Create a temporary repository with Python files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Create src directory structure
        src_path = repo_path / "src" / "myproject"
        src_path.mkdir(parents=True)
        
        # Create a module with classes and functions
        (src_path / "utils.py").write_text('''
"""Utility functions for the project."""

import os
from typing import Optional


class Helper:
    """A helper class for common operations."""
    
    def __init__(self, name: str):
        self.name = name
    
    async def process(self, data: str) -> str:
        """Process the input data."""
        return data.upper()
    
    def cleanup(self):
        """Clean up resources."""
        pass


def calculate_something(x: int, y: int) -> int:
    """Calculate something from x and y."""
    return x + y


def untested_function():
    pass
''')
        
        # Create another module that imports from utils
        (src_path / "main.py").write_text('''
"""Main application module."""

from myproject.utils import Helper, calculate_something
import os


class Application:
    """Main application class."""
    
    def run(self):
        helper = Helper("test")
        result = calculate_something(1, 2)
        return result
''')
        
        # Create tests
        tests_path = repo_path / "tests"
        tests_path.mkdir()
        
        (tests_path / "test_utils.py").write_text('''
"""Tests for utils module."""

import pytest
from myproject.utils import Helper, calculate_something


def test_helper_process():
    helper = Helper("test")
    assert helper.process("hello") == "HELLO"


def test_calculate_something():
    assert calculate_something(2, 3) == 5
''')
        
        yield repo_path


@pytest.fixture
def indexer(temp_repo):
    """Create CodebaseIndexer for temp repo."""
    import uuid
    return CodebaseIndexer(
        repo_path=temp_repo,
        db_path=temp_repo / f"test_index_{uuid.uuid4().hex[:8]}.db",
        src_dirs=["src", "tests"],
    )


@pytest.mark.asyncio
class TestCodebaseIndexerBasics:
    """Basic indexing functionality."""
    
    async def test_index_all_counts(self, indexer):
        """Should index all Python files."""
        stats = await indexer.index_all()
        
        assert stats["indexed"] == 3  # utils.py, main.py, test_utils.py
        assert stats["failed"] == 0
    
    async def test_index_skips_unchanged(self, indexer):
        """Should skip unchanged files on second run."""
        await indexer.index_all()
        
        # Second index should skip all
        stats = await indexer.index_all()
        assert stats["skipped"] == 3
        assert stats["indexed"] == 0
    
    async def test_index_changed_detects_updates(self, indexer, temp_repo):
        """Should reindex changed files."""
        await indexer.index_all()
        
        # Modify a file
        utils_path = temp_repo / "src" / "myproject" / "utils.py"
        content = utils_path.read_text()
        utils_path.write_text(content + "\n# Modified\n")
        
        # Incremental index should detect change
        stats = await indexer.index_changed()
        assert stats["indexed"] == 1
        assert stats["skipped"] == 2


@pytest.mark.asyncio
class TestCodebaseIndexerParsing:
    """AST parsing accuracy."""
    
    async def test_parses_classes(self, indexer):
        """Should extract class information."""
        await indexer.index_all()
        
        info = await indexer.get_module_info("src/myproject/utils.py")
        assert info is not None
        
        class_names = [c.name for c in info.classes]
        assert "Helper" in class_names
    
    async def test_parses_class_methods(self, indexer):
        """Should extract class methods."""
        await indexer.index_all()
        
        info = await indexer.get_module_info("src/myproject/utils.py")
        helper = [c for c in info.classes if c.name == "Helper"][0]
        
        method_names = [m.name for m in helper.methods]
        assert "process" in method_names
        assert "cleanup" in method_names
    
    async def test_parses_function_signatures(self, indexer):
        """Should extract function signatures."""
        await indexer.index_all()
        
        info = await indexer.get_module_info("src/myproject/utils.py")
        
        func_names = [f.name for f in info.functions]
        assert "calculate_something" in func_names
        assert "untested_function" in func_names
        
        # Check signature details
        calc_func = [f for f in info.functions if f.name == "calculate_something"][0]
        assert calc_func.returns == "int"
        assert "x" in calc_func.args[0] if calc_func.args else True
    
    async def test_parses_imports(self, indexer):
        """Should extract import statements."""
        await indexer.index_all()
        
        info = await indexer.get_module_info("src/myproject/main.py")
        
        assert "myproject.utils.Helper" in info.imports
        assert "myproject.utils.calculate_something" in info.imports
        assert "os" in info.imports
    
    async def test_parses_docstrings(self, indexer):
        """Should extract module and class docstrings."""
        await indexer.index_all()
        
        info = await indexer.get_module_info("src/myproject/utils.py")
        
        assert "Utility functions" in info.docstring
        assert "helper class" in info.classes[0].docstring.lower()


@pytest.mark.asyncio
class TestCodebaseIndexerTestCoverage:
    """Test coverage mapping."""
    
    async def test_maps_test_files(self, indexer):
        """Should map source files to test files."""
        await indexer.index_all()
        
        info = await indexer.get_module_info("src/myproject/utils.py")
        
        assert info.test_coverage is not None
        assert "test_utils.py" in info.test_coverage
    
    async def test_has_test_coverage_method(self, indexer):
        """Should check if file has test coverage."""
        await indexer.index_all()
        
        assert await indexer.has_test_coverage("src/myproject/utils.py") is True
        # main.py has no corresponding test file
        assert await indexer.has_test_coverage("src/myproject/main.py") is False


@pytest.mark.asyncio
class TestCodebaseIndexerDependencies:
    """Dependency graph building."""
    
    async def test_builds_dependency_graph(self, indexer):
        """Should build import dependency graph."""
        await indexer.index_all()
        
        # main.py imports from utils.py
        deps = await indexer.get_dependency_chain("src/myproject/utils.py")
        
        assert "src/myproject/main.py" in deps
    
    async def test_empty_dependency_chain(self, indexer):
        """Should return empty list for files with no dependents."""
        await indexer.index_all()
        
        # test_utils.py likely doesn't have dependents
        deps = await indexer.get_dependency_chain("tests/test_utils.py")
        
        assert deps == []


@pytest.mark.asyncio
class TestCodebaseIndexerSummary:
    """Summary generation."""
    
    async def test_generates_summary(self, indexer):
        """Should generate codebase summary."""
        await indexer.index_all()
        
        summary = await indexer.get_summary()
        
        assert "Codebase Summary" in summary
        assert "myproject.utils" in summary
        assert "Helper" in summary
        assert "calculate_something" in summary
    
    async def test_summary_respects_max_tokens(self, indexer):
        """Should truncate if summary exceeds max tokens."""
        await indexer.index_all()
        
        # Very small limit
        summary = await indexer.get_summary(max_tokens=10)
        
        assert len(summary) <= 10 * 4 + 100  # rough check with buffer


@pytest.mark.asyncio
class TestCodebaseIndexerRelevance:
    """Relevant file search."""
    
    async def test_finds_relevant_files(self, indexer):
        """Should find files relevant to task description."""
        await indexer.index_all()
        
        files = await indexer.get_relevant_files("calculate something with helper", limit=5)
        
        assert "src/myproject/utils.py" in files
    
    async def test_relevance_scoring(self, indexer):
        """Should score files by keyword match."""
        await indexer.index_all()
        
        files = await indexer.get_relevant_files("process data with helper", limit=5)
        
        # utils.py should be first (has Helper class with process method)
        assert files[0] == "src/myproject/utils.py"
    
    async def test_returns_empty_for_no_matches(self, indexer):
        """Should return empty list when no files match."""
        await indexer.index_all()
        
        # Use truly unique keywords that won't match anything in the codebase
        files = await indexer.get_relevant_files("astronaut dinosaur zebra unicorn", limit=5)
        
        assert files == []


@pytest.mark.asyncio
class TestCodebaseIndexerIntegration:
    """Full workflow integration tests."""
    
    async def test_full_index_query_workflow(self, temp_repo):
        """Complete workflow: index, query, get dependencies."""
        indexer = CodebaseIndexer(
            repo_path=temp_repo,
            db_path=temp_repo / "integration.db",
            src_dirs=["src", "tests"],
        )
        
        # Index all files
        stats = await indexer.index_all()
        assert stats["indexed"] == 3
        
        # Get summary
        summary = await indexer.get_summary()
        assert "Helper" in summary
        
        # Find relevant files
        files = await indexer.get_relevant_files("helper class", limit=3)
        assert len(files) > 0
        
        # Check dependencies
        deps = await indexer.get_dependency_chain("src/myproject/utils.py")
        assert "src/myproject/main.py" in deps
        
        # Verify test coverage
        has_tests = await indexer.has_test_coverage("src/myproject/utils.py")
        assert has_tests is True
    
    async def test_handles_syntax_errors_gracefully(self, temp_repo):
        """Should skip files with syntax errors."""
        # Create a file with syntax error
        (temp_repo / "src" / "bad.py").write_text("def broken(:")
        
        indexer = CodebaseIndexer(
            repo_path=temp_repo,
            db_path=temp_repo / "syntax_error.db",
            src_dirs=["src"],
        )
        
        stats = await indexer.index_all()
        
        # Should index the good files, fail on bad one
        assert stats["failed"] == 1
        assert stats["indexed"] >= 2
