"""Self-Coding Layer — Timmy's ability to modify its own source code safely.

This module provides the foundational infrastructure for self-modification:

- GitSafety: Atomic git operations with rollback capability
- CodebaseIndexer: Live mental model of the codebase
- ModificationJournal: Persistent log of modification attempts
- ReflectionService: Generate lessons learned from attempts

Usage:
    from self_coding import GitSafety, CodebaseIndexer, ModificationJournal
    from self_coding import ModificationAttempt, Outcome, Snapshot
    
    # Initialize services
    git = GitSafety(repo_path="/path/to/repo")
    indexer = CodebaseIndexer(repo_path="/path/to/repo")
    journal = ModificationJournal()
    
    # Use in self-modification workflow
    snapshot = await git.snapshot()
    # ... make changes ...
    if tests_pass:
        await git.commit("Changes", ["file.py"])
    else:
        await git.rollback(snapshot)
"""

from self_coding.git_safety import GitSafety, Snapshot
from self_coding.codebase_indexer import CodebaseIndexer, ModuleInfo, FunctionInfo, ClassInfo
from self_coding.modification_journal import (
    ModificationJournal,
    ModificationAttempt,
    Outcome,
)
from self_coding.reflection import ReflectionService

__all__ = [
    # Core services
    "GitSafety",
    "CodebaseIndexer",
    "ModificationJournal",
    "ReflectionService",
    # Data classes
    "Snapshot",
    "ModuleInfo",
    "FunctionInfo",
    "ClassInfo",
    "ModificationAttempt",
    "Outcome",
]