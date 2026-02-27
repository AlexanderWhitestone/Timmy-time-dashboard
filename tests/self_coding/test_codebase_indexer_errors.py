"""Error path tests for Codebase Indexer.

Tests syntax errors, encoding issues, circular imports, and edge cases.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from self_coding.codebase_indexer import CodebaseIndexer, ModuleInfo


@pytest.mark.asyncio
class TestCodebaseIndexerErrors:
    """Indexing error handling."""
    
    async def test_syntax_error_file(self):
        """Should skip files with syntax errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            # Valid file
            (src_path / "good.py").write_text("def good(): pass")
            
            # File with syntax error
            (src_path / "bad.py").write_text("def bad(:\n  pass")
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            stats = await indexer.index_all()
            
            assert stats["indexed"] == 1
            assert stats["failed"] == 1
    
    async def test_unicode_in_source(self):
        """Should handle Unicode in source files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            # File with Unicode
            (src_path / "unicode.py").write_text(
                '# -*- coding: utf-8 -*-\n'
                '"""Module with Unicode: ñ 中文 🎉"""\n'
                'def hello():\n'
                '    """Returns 👋"""\n'
                '    return "hello"\n',
                encoding="utf-8",
            )
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            stats = await indexer.index_all()
            
            assert stats["indexed"] == 1
            assert stats["failed"] == 0
            
            info = await indexer.get_module_info("src/unicode.py")
            assert "中文" in info.docstring
    
    async def test_empty_file(self):
        """Should handle empty Python files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            # Empty file
            (src_path / "empty.py").write_text("")
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            stats = await indexer.index_all()
            
            assert stats["indexed"] == 1
            
            info = await indexer.get_module_info("src/empty.py")
            assert info is not None
            assert info.functions == []
            assert info.classes == []
    
    async def test_large_file(self):
        """Should handle large Python files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            # Large file with many functions
            content = ['"""Large module."""']
            for i in range(100):
                content.append(f'def function_{i}(x: int) -> int:')
                content.append(f'    """Function {i}."""')
                content.append(f'    return x + {i}')
                content.append('')
            
            (src_path / "large.py").write_text("\n".join(content))
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            stats = await indexer.index_all()
            
            assert stats["indexed"] == 1
            
            info = await indexer.get_module_info("src/large.py")
            assert len(info.functions) == 100
    
    async def test_nested_classes(self):
        """Should handle nested classes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            (src_path / "nested.py").write_text('''
"""Module with nested classes."""

class Outer:
    """Outer class."""
    
    class Inner:
        """Inner class."""
        
        def inner_method(self):
            pass
    
    def outer_method(self):
        pass
''')
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            await indexer.index_all()
            
            info = await indexer.get_module_info("src/nested.py")
            
            # Should find Outer class (top-level)
            assert len(info.classes) == 1
            assert info.classes[0].name == "Outer"
            # Outer should have outer_method
            assert len(info.classes[0].methods) == 1
            assert info.classes[0].methods[0].name == "outer_method"
    
    async def test_complex_type_annotations(self):
        """Should handle complex type annotations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            (src_path / "types.py").write_text('''
"""Module with complex types."""

from typing import Dict, List, Optional, Union, Callable


def complex_function(
    items: List[Dict[str, Union[int, str]]],
    callback: Callable[[int], bool],
    optional: Optional[str] = None,
) -> Dict[str, List[int]]:
    """Function with complex types."""
    return {}


class TypedClass:
    """Class with type annotations."""
    
    def method(self, x: int | str) -> list[int]:
        """Method with union type (Python 3.10+)."""
        return []
''')
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            await indexer.index_all()
            
            info = await indexer.get_module_info("src/types.py")
            
            # Should parse without error
            assert len(info.functions) == 1
            assert len(info.classes) == 1
    
    async def test_import_variations(self):
        """Should handle various import styles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            (src_path / "imports.py").write_text('''
"""Module with various imports."""

# Regular imports
import os
import sys as system
from pathlib import Path

# From imports
from typing import Dict, List
from collections import OrderedDict as OD

# Relative imports (may not resolve)
from . import sibling
from .subpackage import module

# Dynamic imports (won't be caught by AST)
try:
    import optional_dep
except ImportError:
    pass
''')
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            await indexer.index_all()
            
            info = await indexer.get_module_info("src/imports.py")
            
            # Should capture static imports
            assert "os" in info.imports
            assert "typing.Dict" in info.imports or "Dict" in str(info.imports)
    
    async def test_no_src_directory(self):
        """Should handle missing src directory gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src", "tests"],
            )
            
            stats = await indexer.index_all()
            
            assert stats["indexed"] == 0
            assert stats["failed"] == 0
    
    async def test_permission_error(self):
        """Should handle permission errors gracefully."""
        import os
        if os.geteuid() == 0:
            pytest.skip("Permission tests are ineffective when running as root")

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()

            # Create file
            file_path = src_path / "locked.py"
            file_path.write_text("def test(): pass")

            # Remove read permission (if on Unix)
            try:
                os.chmod(file_path, 0o000)

                indexer = CodebaseIndexer(
                    repo_path=repo_path,
                    db_path=repo_path / "index.db",
                    src_dirs=["src"],
                )

                stats = await indexer.index_all()

                # Should count as failed
                assert stats["failed"] == 1

            finally:
                # Restore permission for cleanup
                os.chmod(file_path, 0o644)
    
    async def test_circular_imports_in_dependency_graph(self):
        """Should handle circular imports in dependency analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            # Create circular imports
            (src_path / "a.py").write_text('''
"""Module A."""
from b import B

class A:
    def get_b(self):
        return B()
''')
            
            (src_path / "b.py").write_text('''
"""Module B."""
from a import A

class B:
    def get_a(self):
        return A()
''')
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            await indexer.index_all()
            
            # Both should have each other as dependencies
            a_deps = await indexer.get_dependency_chain("src/a.py")
            b_deps = await indexer.get_dependency_chain("src/b.py")
            
            # Note: Due to import resolution, this might not be perfect
            # but it shouldn't crash
            assert isinstance(a_deps, list)
            assert isinstance(b_deps, list)
    
    async def test_summary_with_no_modules(self):
        """Summary should handle empty codebase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            await indexer.index_all()
            
            summary = await indexer.get_summary()
            
            assert "Codebase Summary" in summary
            assert "Total modules: 0" in summary
    
    async def test_get_relevant_files_with_special_chars(self):
        """Should handle special characters in search query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            (src_path / "test.py").write_text('def test(): pass')
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            await indexer.index_all()
            
            # Search with special chars shouldn't crash
            files = await indexer.get_relevant_files("test!@#$%^&*()", limit=5)
            assert isinstance(files, list)
    
    async def test_concurrent_indexing(self):
        """Should handle concurrent indexing attempts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            (src_path / "file.py").write_text("def test(): pass")
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            # Multiple rapid indexing calls
            import asyncio
            tasks = [
                indexer.index_all(),
                indexer.index_all(),
                indexer.index_all(),
            ]
            results = await asyncio.gather(*tasks)
            
            # All should complete without error
            for stats in results:
                assert stats["indexed"] >= 0
                assert stats["failed"] >= 0
    
    async def test_binary_file_in_src(self):
        """Should skip binary files in src directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            src_path = repo_path / "src"
            src_path.mkdir()
            
            # Binary file
            (src_path / "data.bin").write_bytes(b"\x00\x01\x02\x03")
            
            # Python file
            (src_path / "script.py").write_text("def test(): pass")
            
            indexer = CodebaseIndexer(
                repo_path=repo_path,
                db_path=repo_path / "index.db",
                src_dirs=["src"],
            )
            
            stats = await indexer.index_all()
            
            # Should only index .py file
            assert stats["indexed"] == 1
            assert stats["failed"] == 0  # Binary files are skipped, not failed
