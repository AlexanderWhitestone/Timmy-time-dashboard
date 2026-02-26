"""Codebase Indexer — Live mental model of Timmy's own codebase.

Parses Python files using AST to extract classes, functions, imports, and
docstrings. Builds a dependency graph and provides semantic search for
relevant files.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default database location
DEFAULT_DB_PATH = Path("data/self_coding.db")


@dataclass
class FunctionInfo:
    """Information about a function."""
    name: str
    args: list[str]
    returns: Optional[str] = None
    docstring: Optional[str] = None
    line_number: int = 0
    is_async: bool = False
    is_method: bool = False


@dataclass
class ClassInfo:
    """Information about a class."""
    name: str
    methods: list[FunctionInfo] = field(default_factory=list)
    docstring: Optional[str] = None
    line_number: int = 0
    bases: list[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """Information about a Python module."""
    file_path: str
    module_name: str
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    docstring: Optional[str] = None
    test_coverage: Optional[str] = None


class CodebaseIndexer:
    """Indexes Python codebase for self-modification workflows.
    
    Parses all Python files using AST to extract:
    - Module names and structure
    - Class definitions with methods
    - Function signatures with args and return types
    - Import relationships
    - Test coverage mapping
    
    Stores everything in SQLite for fast querying.
    
    Usage:
        indexer = CodebaseIndexer(repo_path="/path/to/repo")
        
        # Full reindex
        await indexer.index_all()
        
        # Incremental update
        await indexer.index_changed()
        
        # Get LLM context summary
        summary = await indexer.get_summary()
        
        # Find relevant files for a task
        files = await indexer.get_relevant_files("Add error handling to health endpoint")
        
        # Get dependency chain
        deps = await indexer.get_dependency_chain("src/timmy/agent.py")
    """
    
    def __init__(
        self,
        repo_path: Optional[str | Path] = None,
        db_path: Optional[str | Path] = None,
        src_dirs: Optional[list[str]] = None,
    ) -> None:
        """Initialize CodebaseIndexer.
        
        Args:
            repo_path: Root of repository to index. Defaults to current directory.
            db_path: SQLite database path. Defaults to data/self_coding.db
            src_dirs: Source directories to index. Defaults to ["src", "tests"]
        """
        self.repo_path = Path(repo_path).resolve() if repo_path else Path.cwd()
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.src_dirs = src_dirs or ["src", "tests"]
        self._ensure_schema()
        logger.info("CodebaseIndexer initialized for %s", self.repo_path)
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection with schema ensured."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_schema(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_conn() as conn:
            # Main codebase index table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS codebase_index (
                    file_path TEXT PRIMARY KEY,
                    module_name TEXT NOT NULL,
                    classes JSON,
                    functions JSON,
                    imports JSON,
                    test_coverage TEXT,
                    last_indexed TIMESTAMP NOT NULL,
                    content_hash TEXT NOT NULL,
                    docstring TEXT,
                    embedding BLOB
                )
                """
            )
            
            # Dependency graph table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dependency_graph (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file TEXT NOT NULL,
                    target_file TEXT NOT NULL,
                    import_type TEXT NOT NULL,
                    UNIQUE(source_file, target_file)
                )
                """
            )
            
            # Create indexes
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_module_name ON codebase_index(module_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_test_coverage ON codebase_index(test_coverage)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deps_source ON dependency_graph(source_file)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deps_target ON dependency_graph(target_file)"
            )
            
            conn.commit()
    
    def _compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of file content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    
    def _find_python_files(self) -> list[Path]:
        """Find all Python files in source directories."""
        files = []
        for src_dir in self.src_dirs:
            src_path = self.repo_path / src_dir
            if src_path.exists():
                files.extend(src_path.rglob("*.py"))
        return sorted(files)
    
    def _find_test_file(self, source_file: Path) -> Optional[str]:
        """Find corresponding test file for a source file.
        
        Uses conventions:
        - src/x/y.py -> tests/test_x_y.py
        - src/x/y.py -> tests/x/test_y.py
        - src/x/y.py -> tests/test_y.py
        """
        rel_path = source_file.relative_to(self.repo_path)
        
        # Only look for tests for files in src/
        if not str(rel_path).startswith("src/"):
            return None
        
        # Try various test file naming conventions
        possible_tests = [
            # tests/test_module.py
            self.repo_path / "tests" / f"test_{source_file.stem}.py",
            # tests/test_path_module.py (flat)
            self.repo_path / "tests" / f"test_{'_'.join(rel_path.with_suffix('').parts[1:])}.py",
        ]
        
        # Try mirroring src structure in tests (tests/x/test_y.py)
        try:
            src_relative = rel_path.relative_to("src")
            possible_tests.append(
                self.repo_path / "tests" / src_relative.parent / f"test_{source_file.stem}.py"
            )
        except ValueError:
            pass
        
        for test_path in possible_tests:
            if test_path.exists():
                return str(test_path.relative_to(self.repo_path))
        
        return None
    
    def _parse_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool = False) -> FunctionInfo:
        """Parse a function definition node."""
        args = []
        
        # Handle different Python versions' AST structures
        func_args = node.args
        
        # Positional args
        for arg in func_args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            args.append(arg_str)
        
        # Keyword-only args
        for arg in func_args.kwonlyargs:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            args.append(arg_str)
        
        # Return type
        returns = None
        if node.returns:
            returns = ast.unparse(node.returns)
        
        # Docstring
        docstring = ast.get_docstring(node)
        
        return FunctionInfo(
            name=node.name,
            args=args,
            returns=returns,
            docstring=docstring,
            line_number=node.lineno,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=is_method,
        )
    
    def _parse_class(self, node: ast.ClassDef) -> ClassInfo:
        """Parse a class definition node."""
        methods = []
        
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._parse_function(item, is_method=True))
        
        # Get bases
        bases = [ast.unparse(base) for base in node.bases]
        
        return ClassInfo(
            name=node.name,
            methods=methods,
            docstring=ast.get_docstring(node),
            line_number=node.lineno,
            bases=bases,
        )
    
    def _parse_module(self, file_path: Path) -> Optional[ModuleInfo]:
        """Parse a Python module file.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            ModuleInfo or None if parsing fails
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            # Compute module name from file path
            rel_path = file_path.relative_to(self.repo_path)
            module_name = str(rel_path.with_suffix("")).replace("/", ".")
            
            classes = []
            functions = []
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}")
            
            # Get top-level definitions (not in classes)
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    classes.append(self._parse_class(node))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(self._parse_function(node))
            
            # Get module docstring
            docstring = ast.get_docstring(tree)
            
            # Find test coverage
            test_coverage = self._find_test_file(file_path)
            
            return ModuleInfo(
                file_path=str(rel_path),
                module_name=module_name,
                classes=classes,
                functions=functions,
                imports=imports,
                docstring=docstring,
                test_coverage=test_coverage,
            )
            
        except SyntaxError as e:
            logger.warning("Syntax error in %s: %s", file_path, e)
            return None
        except Exception as e:
            logger.error("Failed to parse %s: %s", file_path, e)
            return None
    
    def _store_module(self, conn: sqlite3.Connection, module: ModuleInfo, content_hash: str) -> None:
        """Store module info in database."""
        conn.execute(
            """
            INSERT OR REPLACE INTO codebase_index
            (file_path, module_name, classes, functions, imports, test_coverage,
             last_indexed, content_hash, docstring)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                module.file_path,
                module.module_name,
                json.dumps([asdict(c) for c in module.classes]),
                json.dumps([asdict(f) for f in module.functions]),
                json.dumps(module.imports),
                module.test_coverage,
                datetime.now(timezone.utc).isoformat(),
                content_hash,
                module.docstring,
            ),
        )
    
    def _build_dependency_graph(self, conn: sqlite3.Connection) -> None:
        """Build and store dependency graph from imports."""
        # Clear existing graph
        conn.execute("DELETE FROM dependency_graph")
        
        # Get all modules
        rows = conn.execute("SELECT file_path, module_name, imports FROM codebase_index").fetchall()
        
        # Map module names to file paths
        module_to_file = {row["module_name"]: row["file_path"] for row in rows}
        
        # Also map without src/ prefix for package imports like myproject.utils
        module_to_file_alt = {}
        for row in rows:
            module_name = row["module_name"]
            if module_name.startswith("src."):
                alt_name = module_name[4:]  # Remove "src." prefix
                module_to_file_alt[alt_name] = row["file_path"]
        
        # Build dependencies
        for row in rows:
            source_file = row["file_path"]
            imports = json.loads(row["imports"])
            
            for imp in imports:
                # Try to resolve import to a file
                # Handle both "module.name" and "module.name.Class" forms
                
                # First try exact match
                if imp in module_to_file:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO dependency_graph
                        (source_file, target_file, import_type)
                        VALUES (?, ?, ?)
                        """,
                        (source_file, module_to_file[imp], "import"),
                    )
                    continue
                
                # Try alternative name (without src/ prefix)
                if imp in module_to_file_alt:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO dependency_graph
                        (source_file, target_file, import_type)
                        VALUES (?, ?, ?)
                        """,
                        (source_file, module_to_file_alt[imp], "import"),
                    )
                    continue
                
                # Try prefix match (import myproject.utils.Helper -> myproject.utils)
                imp_parts = imp.split(".")
                for i in range(len(imp_parts), 0, -1):
                    prefix = ".".join(imp_parts[:i])
                    
                    # Try original module name
                    if prefix in module_to_file:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO dependency_graph
                            (source_file, target_file, import_type)
                            VALUES (?, ?, ?)
                            """,
                            (source_file, module_to_file[prefix], "import"),
                        )
                        break
                    
                    # Try alternative name (without src/ prefix)
                    if prefix in module_to_file_alt:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO dependency_graph
                            (source_file, target_file, import_type)
                            VALUES (?, ?, ?)
                            """,
                            (source_file, module_to_file_alt[prefix], "import"),
                        )
                        break
        
        conn.commit()
    
    async def index_all(self) -> dict[str, int]:
        """Perform full reindex of all Python files.
        
        Returns:
            Dict with stats: {"indexed": int, "failed": int, "skipped": int}
        """
        logger.info("Starting full codebase index")
        
        files = self._find_python_files()
        stats = {"indexed": 0, "failed": 0, "skipped": 0}
        
        with self._get_conn() as conn:
            for file_path in files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    content_hash = self._compute_hash(content)
                    
                    # Check if file needs reindexing
                    existing = conn.execute(
                        "SELECT content_hash FROM codebase_index WHERE file_path = ?",
                        (str(file_path.relative_to(self.repo_path)),),
                    ).fetchone()
                    
                    if existing and existing["content_hash"] == content_hash:
                        stats["skipped"] += 1
                        continue
                    
                    module = self._parse_module(file_path)
                    if module:
                        self._store_module(conn, module, content_hash)
                        stats["indexed"] += 1
                    else:
                        stats["failed"] += 1
                        
                except Exception as e:
                    logger.error("Failed to index %s: %s", file_path, e)
                    stats["failed"] += 1
            
            # Build dependency graph
            self._build_dependency_graph(conn)
            conn.commit()
        
        logger.info(
            "Indexing complete: %(indexed)d indexed, %(failed)d failed, %(skipped)d skipped",
            stats,
        )
        return stats
    
    async def index_changed(self) -> dict[str, int]:
        """Perform incremental index of only changed files.
        
        Compares content hashes to detect changes.
        
        Returns:
            Dict with stats: {"indexed": int, "failed": int, "skipped": int}
        """
        logger.info("Starting incremental codebase index")
        
        files = self._find_python_files()
        stats = {"indexed": 0, "failed": 0, "skipped": 0}
        
        with self._get_conn() as conn:
            for file_path in files:
                try:
                    rel_path = str(file_path.relative_to(self.repo_path))
                    content = file_path.read_text(encoding="utf-8")
                    content_hash = self._compute_hash(content)
                    
                    # Check if changed
                    existing = conn.execute(
                        "SELECT content_hash FROM codebase_index WHERE file_path = ?",
                        (rel_path,),
                    ).fetchone()
                    
                    if existing and existing["content_hash"] == content_hash:
                        stats["skipped"] += 1
                        continue
                    
                    module = self._parse_module(file_path)
                    if module:
                        self._store_module(conn, module, content_hash)
                        stats["indexed"] += 1
                    else:
                        stats["failed"] += 1
                        
                except Exception as e:
                    logger.error("Failed to index %s: %s", file_path, e)
                    stats["failed"] += 1
            
            # Rebuild dependency graph (some imports may have changed)
            self._build_dependency_graph(conn)
            conn.commit()
        
        logger.info(
            "Incremental indexing complete: %(indexed)d indexed, %(failed)d failed, %(skipped)d skipped",
            stats,
        )
        return stats
    
    async def get_summary(self, max_tokens: int = 4000) -> str:
        """Generate compressed codebase summary for LLM context.
        
        Lists modules, their purposes, key classes/functions, and test coverage.
        Keeps output under max_tokens (approximate).
        
        Args:
            max_tokens: Maximum approximate tokens for summary
            
        Returns:
            Summary string suitable for LLM context
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT file_path, module_name, classes, functions, test_coverage, docstring
                FROM codebase_index
                ORDER BY module_name
                """
            ).fetchall()
        
        lines = ["# Codebase Summary\n"]
        lines.append(f"Total modules: {len(rows)}\n")
        lines.append("---\n")
        
        for row in rows:
            module_name = row["module_name"]
            file_path = row["file_path"]
            docstring = row["docstring"]
            test_coverage = row["test_coverage"]
            
            lines.append(f"\n## {module_name}")
            lines.append(f"File: `{file_path}`")
            
            if test_coverage:
                lines.append(f"Tests: `{test_coverage}`")
            else:
                lines.append("Tests: None")
            
            if docstring:
                # Take first line of docstring
                first_line = docstring.split("\n")[0][:100]
                lines.append(f"Purpose: {first_line}")
            
            # Classes
            classes = json.loads(row["classes"])
            if classes:
                lines.append("Classes:")
                for cls in classes[:5]:  # Limit to 5 classes
                    methods = [m["name"] for m in cls["methods"][:3]]
                    method_str = ", ".join(methods) + ("..." if len(cls["methods"]) > 3 else "")
                    lines.append(f"  - {cls['name']}({method_str})")
                if len(classes) > 5:
                    lines.append(f"  ... and {len(classes) - 5} more")
            
            # Functions
            functions = json.loads(row["functions"])
            if functions:
                func_names = [f["name"] for f in functions[:5]]
                func_str = ", ".join(func_names)
                if len(functions) > 5:
                    func_str += f"... and {len(functions) - 5} more"
                lines.append(f"Functions: {func_str}")
            
            lines.append("")
        
        summary = "\n".join(lines)
        
        # Rough token estimation (1 token ≈ 4 characters)
        if len(summary) > max_tokens * 4:
            # Truncate with note
            summary = summary[:max_tokens * 4]
            summary += "\n\n[Summary truncated due to length]"
        
        return summary
    
    async def get_relevant_files(self, task_description: str, limit: int = 5) -> list[str]:
        """Find files relevant to a task description.
        
        Uses keyword matching and import relationships. In Phase 2,
        this will use semantic search with vector embeddings.
        
        Args:
            task_description: Natural language description of the task
            limit: Maximum number of files to return
            
        Returns:
            List of file paths sorted by relevance
        """
        # Simple keyword extraction for now
        keywords = set(task_description.lower().split())
        # Remove common words
        keywords -= {"the", "a", "an", "to", "in", "on", "at", "for", "with", "and", "or", "of", "is", "are"}
        
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT file_path, module_name, classes, functions, docstring, test_coverage
                FROM codebase_index
                """
            ).fetchall()
        
        scored_files = []
        
        for row in rows:
            score = 0
            file_path = row["file_path"].lower()
            module_name = row["module_name"].lower()
            docstring = (row["docstring"] or "").lower()
            
            classes = json.loads(row["classes"])
            functions = json.loads(row["functions"])
            
            # Score based on keyword matches
            for keyword in keywords:
                if keyword in file_path:
                    score += 3
                if keyword in module_name:
                    score += 2
                if keyword in docstring:
                    score += 2
                
                # Check class/function names
                for cls in classes:
                    if keyword in cls["name"].lower():
                        score += 2
                    for method in cls["methods"]:
                        if keyword in method["name"].lower():
                            score += 1
                
                for func in functions:
                    if keyword in func["name"].lower():
                        score += 1
            
            # Boost files with test coverage (only if already matched)
            if score > 0 and row["test_coverage"]:
                score += 1
            
            if score > 0:
                scored_files.append((score, row["file_path"]))
        
        # Sort by score descending, return top N
        scored_files.sort(reverse=True, key=lambda x: x[0])
        return [f[1] for f in scored_files[:limit]]
    
    async def get_dependency_chain(self, file_path: str) -> list[str]:
        """Get all files that import the given file.
        
        Useful for understanding blast radius of changes.
        
        Args:
            file_path: Path to file (relative to repo root)
            
        Returns:
            List of file paths that import this file
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT source_file FROM dependency_graph
                WHERE target_file = ?
                """,
                (file_path,),
            ).fetchall()
        
        return [row["source_file"] for row in rows]
    
    async def has_test_coverage(self, file_path: str) -> bool:
        """Check if a file has corresponding test coverage.
        
        Args:
            file_path: Path to file (relative to repo root)
            
        Returns:
            True if test file exists, False otherwise
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT test_coverage FROM codebase_index WHERE file_path = ?",
                (file_path,),
            ).fetchone()
        
        return row is not None and row["test_coverage"] is not None
    
    async def get_module_info(self, file_path: str) -> Optional[ModuleInfo]:
        """Get detailed info for a specific module.
        
        Args:
            file_path: Path to file (relative to repo root)
            
        Returns:
            ModuleInfo or None if not indexed
        """
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT file_path, module_name, classes, functions, imports,
                       test_coverage, docstring
                FROM codebase_index
                WHERE file_path = ?
                """,
                (file_path,),
            ).fetchone()
        
        if not row:
            return None
        
        # Parse classes - convert dict methods to FunctionInfo objects
        classes_data = json.loads(row["classes"])
        classes = []
        for cls_data in classes_data:
            methods = [FunctionInfo(**m) for m in cls_data.get("methods", [])]
            cls_info = ClassInfo(
                name=cls_data["name"],
                methods=methods,
                docstring=cls_data.get("docstring"),
                line_number=cls_data.get("line_number", 0),
                bases=cls_data.get("bases", []),
            )
            classes.append(cls_info)
        
        # Parse functions
        functions_data = json.loads(row["functions"])
        functions = [FunctionInfo(**f) for f in functions_data]
        
        return ModuleInfo(
            file_path=row["file_path"],
            module_name=row["module_name"],
            classes=classes,
            functions=functions,
            imports=json.loads(row["imports"]),
            docstring=row["docstring"],
            test_coverage=row["test_coverage"],
        )
