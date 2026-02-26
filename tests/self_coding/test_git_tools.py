"""Tests for tools.git_tools — Git operations for Forge/Helm personas.

All tests use temporary git repositories to avoid touching the real
working tree.
"""

import pytest
from pathlib import Path

from creative.tools.git_tools import (
    git_init,
    git_status,
    git_add,
    git_commit,
    git_log,
    git_diff,
    git_branch,
    git_stash,
    git_blame,
    git_clone,
    GIT_TOOL_CATALOG,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with one commit."""
    result = git_init(tmp_path)
    assert result["success"]

    # Configure git identity for commits
    from git import Repo
    repo = Repo(str(tmp_path))
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()

    # Create initial commit
    readme = tmp_path / "README.md"
    readme.write_text("# Test Repo\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    return tmp_path


class TestGitInit:
    def test_init_creates_repo(self, tmp_path):
        path = tmp_path / "new_repo"
        result = git_init(path)
        assert result["success"]
        assert (path / ".git").is_dir()

    def test_init_returns_path(self, tmp_path):
        path = tmp_path / "repo"
        result = git_init(path)
        assert result["path"] == str(path)


class TestGitStatus:
    def test_clean_repo(self, git_repo):
        result = git_status(git_repo)
        assert result["success"]
        assert result["is_dirty"] is False
        assert result["untracked"] == []

    def test_dirty_repo_untracked(self, git_repo):
        (git_repo / "new_file.txt").write_text("hello")
        result = git_status(git_repo)
        assert result["is_dirty"] is True
        assert "new_file.txt" in result["untracked"]

    def test_reports_branch(self, git_repo):
        result = git_status(git_repo)
        assert result["branch"] in ("main", "master")


class TestGitAddCommit:
    def test_add_and_commit(self, git_repo):
        (git_repo / "test.py").write_text("print('hi')\n")
        add_result = git_add(git_repo, ["test.py"])
        assert add_result["success"]

        commit_result = git_commit(git_repo, "Add test.py")
        assert commit_result["success"]
        assert len(commit_result["sha"]) == 40
        assert commit_result["message"] == "Add test.py"

    def test_add_all(self, git_repo):
        (git_repo / "a.txt").write_text("a")
        (git_repo / "b.txt").write_text("b")
        result = git_add(git_repo)
        assert result["success"]


class TestGitLog:
    def test_log_returns_commits(self, git_repo):
        result = git_log(git_repo)
        assert result["success"]
        assert len(result["commits"]) >= 1
        first = result["commits"][0]
        assert "sha" in first
        assert "message" in first
        assert "author" in first
        assert "date" in first

    def test_log_max_count(self, git_repo):
        result = git_log(git_repo, max_count=1)
        assert len(result["commits"]) == 1


class TestGitDiff:
    def test_no_diff_on_clean(self, git_repo):
        result = git_diff(git_repo)
        assert result["success"]
        assert result["diff"] == ""

    def test_diff_on_modified(self, git_repo):
        readme = git_repo / "README.md"
        readme.write_text("# Modified\n")
        result = git_diff(git_repo)
        assert result["success"]
        assert "Modified" in result["diff"]


class TestGitBranch:
    def test_list_branches(self, git_repo):
        result = git_branch(git_repo)
        assert result["success"]
        assert len(result["branches"]) >= 1

    def test_create_branch(self, git_repo):
        result = git_branch(git_repo, create="feature-x")
        assert result["success"]
        assert "feature-x" in result["branches"]
        assert result["created"] == "feature-x"

    def test_switch_branch(self, git_repo):
        git_branch(git_repo, create="dev")
        result = git_branch(git_repo, switch="dev")
        assert result["active"] == "dev"


class TestGitStash:
    def test_stash_and_pop(self, git_repo):
        readme = git_repo / "README.md"
        readme.write_text("# Changed\n")

        stash_result = git_stash(git_repo, message="wip")
        assert stash_result["success"]
        assert stash_result["action"] == "stash"

        # Working tree should be clean after stash
        status = git_status(git_repo)
        assert status["is_dirty"] is False

        # Pop restores changes
        pop_result = git_stash(git_repo, pop=True)
        assert pop_result["success"]
        assert pop_result["action"] == "pop"


class TestGitBlame:
    def test_blame_file(self, git_repo):
        result = git_blame(git_repo, "README.md")
        assert result["success"]
        assert "Test Repo" in result["blame"]


class TestGitToolCatalog:
    def test_catalog_has_all_tools(self):
        expected = {
            "git_clone", "git_status", "git_diff", "git_log",
            "git_blame", "git_branch", "git_add", "git_commit",
            "git_push", "git_pull", "git_stash",
        }
        assert expected == set(GIT_TOOL_CATALOG.keys())

    def test_catalog_entries_have_required_keys(self):
        for tool_id, info in GIT_TOOL_CATALOG.items():
            assert "name" in info, f"{tool_id} missing name"
            assert "description" in info, f"{tool_id} missing description"
            assert "fn" in info, f"{tool_id} missing fn"
            assert callable(info["fn"]), f"{tool_id} fn not callable"
