"""Git operations tools for Forge, Helm, and Timmy personas.

Provides a full set of git commands that agents can execute against
the local repository. Uses subprocess with explicit working directory
to ensure commands run from the repo root.

All functions return plain dicts so they're easily serialisable for
tool-call results, Spark event capture, and WebSocket broadcast.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _find_repo_root() -> str:
    """Walk up from this file's location to find the .git directory."""
    path = os.path.dirname(os.path.abspath(__file__))
    # Start from project root (3 levels up from src/tools/git_tools.py)
    path = os.path.dirname(os.path.dirname(os.path.dirname(path)))
    
    while path != os.path.dirname(path):
        if os.path.exists(os.path.join(path, '.git')):
            return path
        path = os.path.dirname(path)
    
    # Fallback to config repo_root
    try:
        from config import settings
        return settings.repo_root
    except Exception:
        return os.getcwd()


# Module-level constant for repo root
REPO_ROOT = _find_repo_root()
logger.info(f"Git repo root: {REPO_ROOT}")


def _run_git_command(args: list[str], cwd: Optional[str] = None) -> tuple[int, str, str]:
    """Run a git command with proper working directory.
    
    Args:
        args: Git command arguments (e.g., ["log", "--oneline", "-5"])
        cwd: Working directory (defaults to REPO_ROOT)
    
    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    cmd = ["git"] + args
    working_dir = cwd or REPO_ROOT
    
    try:
        result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out after 30 seconds"
    except Exception as exc:
        return -1, "", str(exc)


# ── Repository management ────────────────────────────────────────────────────

def git_clone(url: str, dest: str | Path) -> dict:
    """Clone a remote repository to a local path."""
    returncode, stdout, stderr = _run_git_command(
        ["clone", url, str(dest)],
        cwd=None  # Clone uses current directory as parent
    )
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    return {
        "success": True,
        "path": str(dest),
        "message": f"Cloned {url} to {dest}",
    }


def git_init(path: str | Path) -> dict:
    """Initialise a new git repository at *path*."""
    os.makedirs(path, exist_ok=True)
    returncode, stdout, stderr = _run_git_command(["init"], cwd=str(path))
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    return {"success": True, "path": str(path)}


# ── Status / inspection ──────────────────────────────────────────────────────

def git_status(repo_path: Optional[str] = None) -> dict:
    """Return working-tree status: modified, staged, untracked files."""
    cwd = repo_path or REPO_ROOT
    returncode, stdout, stderr = _run_git_command(
        ["status", "--porcelain", "-b"], cwd=cwd
    )
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    # Parse porcelain output
    lines = stdout.strip().split("\n") if stdout else []
    branch = "unknown"
    modified = []
    staged = []
    untracked = []
    
    for line in lines:
        if line.startswith("## "):
            branch = line[3:].split("...")[0].strip()
        elif len(line) >= 2:
            index_status = line[0]
            worktree_status = line[1]
            filename = line[3:].strip() if len(line) > 3 else ""
            
            if index_status in "MADRC":
                staged.append(filename)
            if worktree_status in "MD":
                modified.append(filename)
            if worktree_status == "?":
                untracked.append(filename)
    
    return {
        "success": True,
        "branch": branch,
        "is_dirty": bool(modified or staged or untracked),
        "modified": modified,
        "staged": staged,
        "untracked": untracked,
    }


def git_diff(
    repo_path: Optional[str] = None,
    staged: bool = False,
    file_path: Optional[str] = None,
) -> dict:
    """Show diff of working tree or staged changes."""
    cwd = repo_path or REPO_ROOT
    args = ["diff"]
    if staged:
        args.append("--cached")
    if file_path:
        args.extend(["--", file_path])
    
    returncode, stdout, stderr = _run_git_command(args, cwd=cwd)
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    return {"success": True, "diff": stdout, "staged": staged}


def git_log(
    repo_path: Optional[str] = None,
    max_count: int = 20,
    branch: Optional[str] = None,
) -> dict:
    """Return recent commit history as a list of dicts."""
    cwd = repo_path or REPO_ROOT
    args = ["log", f"--max-count={max_count}", "--format=%H|%h|%s|%an|%ai"]
    if branch:
        args.append(branch)
    
    returncode, stdout, stderr = _run_git_command(args, cwd=cwd)
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    commits = []
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 4)
        if len(parts) >= 5:
            commits.append({
                "sha": parts[0],
                "short_sha": parts[1],
                "message": parts[2],
                "author": parts[3],
                "date": parts[4],
            })
    
    # Get current branch
    _, branch_out, _ = _run_git_command(["branch", "--show-current"], cwd=cwd)
    current_branch = branch_out.strip() or "main"
    
    return {
        "success": True,
        "branch": branch or current_branch,
        "commits": commits,
    }


def git_blame(repo_path: Optional[str] = None, file_path: str = "") -> dict:
    """Show line-by-line authorship for a file."""
    if not file_path:
        return {"success": False, "error": "file_path is required"}
    
    cwd = repo_path or REPO_ROOT
    returncode, stdout, stderr = _run_git_command(
        ["blame", "--porcelain", file_path], cwd=cwd
    )
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    return {"success": True, "file": file_path, "blame": stdout}


# ── Branching ─────────────────────────────────────────────────────────────────

def git_branch(
    repo_path: Optional[str] = None,
    create: Optional[str] = None,
    switch: Optional[str] = None,
) -> dict:
    """List branches, optionally create or switch to one."""
    cwd = repo_path or REPO_ROOT
    
    if create:
        returncode, _, stderr = _run_git_command(
            ["branch", create], cwd=cwd
        )
        if returncode != 0:
            return {"success": False, "error": stderr}
    
    if switch:
        returncode, _, stderr = _run_git_command(
            ["checkout", switch], cwd=cwd
        )
        if returncode != 0:
            return {"success": False, "error": stderr}
    
    # List branches
    returncode, stdout, stderr = _run_git_command(
        ["branch", "-a", "--format=%(refname:short)%(if)%(HEAD)%(then)*%(end)"],
        cwd=cwd
    )
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    branches = []
    active = ""
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if line.endswith("*"):
            active = line[:-1]
            branches.append(active)
        elif line:
            branches.append(line)
    
    return {
        "success": True,
        "branches": branches,
        "active": active,
        "created": create,
        "switched": switch,
    }


# ── Staging & committing ─────────────────────────────────────────────────────

def git_add(repo_path: Optional[str] = None, paths: Optional[list[str]] = None) -> dict:
    """Stage files for commit. *paths* defaults to all modified files."""
    cwd = repo_path or REPO_ROOT
    
    if paths:
        args = ["add"] + paths
    else:
        args = ["add", "-A"]
    
    returncode, _, stderr = _run_git_command(args, cwd=cwd)
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    return {"success": True, "staged": paths or ["all"]}


def git_commit(
    repo_path: Optional[str] = None,
    message: str = "",
) -> dict:
    """Create a commit with the given message."""
    if not message:
        return {"success": False, "error": "commit message is required"}
    
    cwd = repo_path or REPO_ROOT
    returncode, stdout, stderr = _run_git_command(
        ["commit", "-m", message], cwd=cwd
    )
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    # Get the commit hash
    _, hash_out, _ = _run_git_command(["rev-parse", "HEAD"], cwd=cwd)
    commit_hash = hash_out.strip()
    
    return {
        "success": True,
        "sha": commit_hash,
        "short_sha": commit_hash[:8],
        "message": message,
    }


# ── Remote operations ─────────────────────────────────────────────────────────

def git_push(
    repo_path: Optional[str] = None,
    remote: str = "origin",
    branch: Optional[str] = None,
) -> dict:
    """Push the current (or specified) branch to the remote."""
    cwd = repo_path or REPO_ROOT
    args = ["push", remote]
    if branch:
        args.append(branch)
    
    returncode, stdout, stderr = _run_git_command(args, cwd=cwd)
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    return {"success": True, "remote": remote, "branch": branch or "current"}


def git_pull(
    repo_path: Optional[str] = None,
    remote: str = "origin",
    branch: Optional[str] = None,
) -> dict:
    """Pull from the remote into the working tree."""
    cwd = repo_path or REPO_ROOT
    args = ["pull", remote]
    if branch:
        args.append(branch)
    
    returncode, stdout, stderr = _run_git_command(args, cwd=cwd)
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
    return {"success": True, "remote": remote, "branch": branch or "current"}


# ── Stashing ──────────────────────────────────────────────────────────────────

def git_stash(
    repo_path: Optional[str] = None,
    pop: bool = False,
    message: Optional[str] = None,
) -> dict:
    """Stash or pop working-tree changes."""
    cwd = repo_path or REPO_ROOT
    
    if pop:
        returncode, _, stderr = _run_git_command(["stash", "pop"], cwd=cwd)
        if returncode != 0:
            return {"success": False, "error": stderr}
        return {"success": True, "action": "pop"}
    
    args = ["stash", "push"]
    if message:
        args.extend(["-m", message])
    
    returncode, _, stderr = _run_git_command(args, cwd=cwd)
    
    if returncode != 0:
        return {"success": False, "error": stderr}
    
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
