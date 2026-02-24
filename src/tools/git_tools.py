"""Git operations tools for Forge, Helm, and Timmy personas.

Provides a full set of git commands that agents can execute against
local or remote repositories.  Uses GitPython under the hood.

All functions return plain dicts so they're easily serialisable for
tool-call results, Spark event capture, and WebSocket broadcast.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_GIT_AVAILABLE = True
try:
    from git import Repo, InvalidGitRepositoryError, GitCommandNotFound
except ImportError:
    _GIT_AVAILABLE = False


def _require_git() -> None:
    if not _GIT_AVAILABLE:
        raise ImportError(
            "GitPython is not installed. Run: pip install GitPython"
        )


def _open_repo(repo_path: str | Path) -> "Repo":
    """Open an existing git repo at *repo_path*."""
    _require_git()
    return Repo(str(repo_path))


# ── Repository management ────────────────────────────────────────────────────

def git_clone(url: str, dest: str | Path) -> dict:
    """Clone a remote repository to a local path.

    Returns dict with ``path`` and ``default_branch``.
    """
    _require_git()
    repo = Repo.clone_from(url, str(dest))
    return {
        "success": True,
        "path": str(dest),
        "default_branch": repo.active_branch.name,
    }


def git_init(path: str | Path) -> dict:
    """Initialise a new git repository at *path*."""
    _require_git()
    Path(path).mkdir(parents=True, exist_ok=True)
    repo = Repo.init(str(path))
    return {"success": True, "path": str(path), "bare": repo.bare}


# ── Status / inspection ──────────────────────────────────────────────────────

def git_status(repo_path: str | Path) -> dict:
    """Return working-tree status: modified, staged, untracked files."""
    repo = _open_repo(repo_path)
    return {
        "success": True,
        "branch": repo.active_branch.name,
        "is_dirty": repo.is_dirty(untracked_files=True),
        "untracked": repo.untracked_files,
        "modified": [item.a_path for item in repo.index.diff(None)],
        "staged": [item.a_path for item in repo.index.diff("HEAD")],
    }


def git_diff(
    repo_path: str | Path,
    staged: bool = False,
    file_path: Optional[str] = None,
) -> dict:
    """Show diff of working tree or staged changes.

    If *file_path* is given, scope diff to that file only.
    """
    repo = _open_repo(repo_path)
    args: list[str] = []
    if staged:
        args.append("--cached")
    if file_path:
        args.extend(["--", file_path])
    diff_text = repo.git.diff(*args)
    return {"success": True, "diff": diff_text, "staged": staged}


def git_log(
    repo_path: str | Path,
    max_count: int = 20,
    branch: Optional[str] = None,
) -> dict:
    """Return recent commit history as a list of dicts."""
    repo = _open_repo(repo_path)
    ref = branch or repo.active_branch.name
    commits = []
    for commit in repo.iter_commits(ref, max_count=max_count):
        commits.append({
            "sha": commit.hexsha,
            "short_sha": commit.hexsha[:8],
            "message": commit.message.strip(),
            "author": str(commit.author),
            "date": commit.committed_datetime.isoformat(),
            "files_changed": len(commit.stats.files),
        })
    return {"success": True, "branch": ref, "commits": commits}


def git_blame(repo_path: str | Path, file_path: str) -> dict:
    """Show line-by-line authorship for a file."""
    repo = _open_repo(repo_path)
    blame_text = repo.git.blame(file_path)
    return {"success": True, "file": file_path, "blame": blame_text}


# ── Branching ─────────────────────────────────────────────────────────────────

def git_branch(
    repo_path: str | Path,
    create: Optional[str] = None,
    switch: Optional[str] = None,
) -> dict:
    """List branches, optionally create or switch to one."""
    repo = _open_repo(repo_path)

    if create:
        repo.create_head(create)
    if switch:
        repo.heads[switch].checkout()

    branches = [h.name for h in repo.heads]
    active = repo.active_branch.name
    return {
        "success": True,
        "branches": branches,
        "active": active,
        "created": create,
        "switched": switch,
    }


# ── Staging & committing ─────────────────────────────────────────────────────

def git_add(repo_path: str | Path, paths: list[str] | None = None) -> dict:
    """Stage files for commit.  *paths* defaults to all modified files."""
    repo = _open_repo(repo_path)
    if paths:
        repo.index.add(paths)
    else:
        # Stage all changes
        repo.git.add(A=True)
    staged = [item.a_path for item in repo.index.diff("HEAD")]
    return {"success": True, "staged": staged}


def git_commit(repo_path: str | Path, message: str) -> dict:
    """Create a commit with the given message."""
    repo = _open_repo(repo_path)
    commit = repo.index.commit(message)
    return {
        "success": True,
        "sha": commit.hexsha,
        "short_sha": commit.hexsha[:8],
        "message": message,
    }


# ── Remote operations ─────────────────────────────────────────────────────────

def git_push(
    repo_path: str | Path,
    remote: str = "origin",
    branch: Optional[str] = None,
) -> dict:
    """Push the current (or specified) branch to the remote."""
    repo = _open_repo(repo_path)
    ref = branch or repo.active_branch.name
    info = repo.remotes[remote].push(ref)
    summaries = [str(i.summary) for i in info]
    return {"success": True, "remote": remote, "branch": ref, "summaries": summaries}


def git_pull(
    repo_path: str | Path,
    remote: str = "origin",
    branch: Optional[str] = None,
) -> dict:
    """Pull from the remote into the working tree."""
    repo = _open_repo(repo_path)
    ref = branch or repo.active_branch.name
    info = repo.remotes[remote].pull(ref)
    summaries = [str(i.summary) for i in info]
    return {"success": True, "remote": remote, "branch": ref, "summaries": summaries}


# ── Stashing ──────────────────────────────────────────────────────────────────

def git_stash(
    repo_path: str | Path,
    pop: bool = False,
    message: Optional[str] = None,
) -> dict:
    """Stash or pop working-tree changes."""
    repo = _open_repo(repo_path)
    if pop:
        repo.git.stash("pop")
        return {"success": True, "action": "pop"}
    args = ["push"]
    if message:
        args.extend(["-m", message])
    repo.git.stash(*args)
    return {"success": True, "action": "stash", "message": message}


# ── Tool catalogue ────────────────────────────────────────────────────────────

GIT_TOOL_CATALOG: dict[str, dict] = {
    "git_clone": {
        "name": "Git Clone",
        "description": "Clone a remote repository to a local path",
        "fn": git_clone,
    },
    "git_status": {
        "name": "Git Status",
        "description": "Show working tree status (modified, staged, untracked)",
        "fn": git_status,
    },
    "git_diff": {
        "name": "Git Diff",
        "description": "Show diff of working tree or staged changes",
        "fn": git_diff,
    },
    "git_log": {
        "name": "Git Log",
        "description": "Show recent commit history",
        "fn": git_log,
    },
    "git_blame": {
        "name": "Git Blame",
        "description": "Show line-by-line authorship for a file",
        "fn": git_blame,
    },
    "git_branch": {
        "name": "Git Branch",
        "description": "List, create, or switch branches",
        "fn": git_branch,
    },
    "git_add": {
        "name": "Git Add",
        "description": "Stage files for commit",
        "fn": git_add,
    },
    "git_commit": {
        "name": "Git Commit",
        "description": "Create a commit with a message",
        "fn": git_commit,
    },
    "git_push": {
        "name": "Git Push",
        "description": "Push branch to remote repository",
        "fn": git_push,
    },
    "git_pull": {
        "name": "Git Pull",
        "description": "Pull from remote repository",
        "fn": git_pull,
    },
    "git_stash": {
        "name": "Git Stash",
        "description": "Stash or pop working tree changes",
        "fn": git_stash,
    },
}
