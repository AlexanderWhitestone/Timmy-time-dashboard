"""Tests for the Git Hand.

Covers:
- Destructive operation gating
- Successful git operations (status, log)
- Convenience wrappers
- GitResult dataclass defaults
- Info summary
"""

import pytest


# ---------------------------------------------------------------------------
# Destructive operation gating
# ---------------------------------------------------------------------------

def test_is_destructive_detects_force_push():
    """Force-push should be flagged as destructive."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    assert hand._is_destructive("push --force origin main") is True
    assert hand._is_destructive("push -f origin main") is True


def test_is_destructive_detects_hard_reset():
    """Hard reset should be flagged as destructive."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    assert hand._is_destructive("reset --hard HEAD~1") is True


def test_is_destructive_safe_ops():
    """Safe operations should not be flagged."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    assert hand._is_destructive("status") is False
    assert hand._is_destructive("log --oneline -5") is False
    assert hand._is_destructive("push origin main") is False
    assert hand._is_destructive("commit -m 'test'") is False


@pytest.mark.asyncio
async def test_run_blocks_destructive_by_default():
    """Destructive ops should be blocked unless allow_destructive=True."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    result = await hand.run("push --force origin main")
    assert result.success is False
    assert result.requires_confirmation is True
    assert "blocked" in result.error.lower()


@pytest.mark.asyncio
async def test_run_allows_destructive_with_flag():
    """Destructive ops should execute when allow_destructive=True."""
    from infrastructure.hands.git import GitHand

    # This will fail because there's no remote, but it should NOT be blocked
    hand = GitHand()
    result = await hand.run("push --force origin nonexistent-branch", allow_destructive=True)
    # It will fail (no remote), but it was NOT blocked by the gate
    assert result.requires_confirmation is False


# ---------------------------------------------------------------------------
# Successful operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_git_status():
    """git status should succeed in a git repo."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    result = await hand.run("status --short")
    assert result.success is True
    assert result.latency_ms > 0


@pytest.mark.asyncio
async def test_run_git_log():
    """git log should succeed in a git repo."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    result = await hand.run("log --oneline -3")
    assert result.success is True
    assert result.output  # should have at least one commit


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_wrapper():
    """status() convenience wrapper should work."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    result = await hand.status()
    assert result.success is True
    assert result.operation == "git status --short"


@pytest.mark.asyncio
async def test_log_wrapper():
    """log() convenience wrapper should work."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    result = await hand.log(count=3)
    assert result.success is True
    assert "git log" in result.operation


@pytest.mark.asyncio
async def test_diff_wrapper():
    """diff() convenience wrapper should work."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    result = await hand.diff()
    assert result.success is True
    assert result.operation == "git diff"


@pytest.mark.asyncio
async def test_diff_staged_wrapper():
    """diff(staged=True) should pass --cached."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    result = await hand.diff(staged=True)
    assert result.success is True
    assert result.operation == "git diff --cached"


# ---------------------------------------------------------------------------
# GitResult dataclass
# ---------------------------------------------------------------------------

def test_git_result_defaults():
    """GitResult should have sensible defaults."""
    from infrastructure.hands.git import GitResult

    r = GitResult(operation="git status", success=True)
    assert r.output == ""
    assert r.error == ""
    assert r.latency_ms == 0.0
    assert r.requires_confirmation is False
    assert r.metadata == {}


# ---------------------------------------------------------------------------
# Info summary
# ---------------------------------------------------------------------------

def test_info_returns_summary():
    """info() should return a dict with repo_dir and timeout."""
    from infrastructure.hands.git import GitHand

    hand = GitHand()
    i = hand.info()
    assert "repo_dir" in i
    assert "default_timeout" in i


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def test_persona_hand_map():
    """Forge and Helm should have both shell and git access."""
    from infrastructure.hands.tools import get_local_hands_for_persona

    forge_hands = get_local_hands_for_persona("forge")
    assert "hand_shell" in forge_hands
    assert "hand_git" in forge_hands

    helm_hands = get_local_hands_for_persona("helm")
    assert "hand_shell" in helm_hands
    assert "hand_git" in helm_hands

    # Echo only gets git
    echo_hands = get_local_hands_for_persona("echo")
    assert "hand_git" in echo_hands
    assert "hand_shell" not in echo_hands

    # Quill gets neither
    quill_hands = get_local_hands_for_persona("quill")
    assert quill_hands == []
