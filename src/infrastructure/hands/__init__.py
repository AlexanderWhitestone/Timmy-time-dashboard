"""Hands — local execution capabilities for Timmy.

Unlike OpenFang (vendored binary sidecar), these hands run in-process
and provide direct shell and git execution with sandboxing and approval
gates.

Usage:
    from infrastructure.hands import shell_hand, git_hand

    result = await shell_hand.run("make test")
    result = await git_hand.run("status")
"""

from infrastructure.hands.shell import shell_hand
from infrastructure.hands.git import git_hand

__all__ = ["shell_hand", "git_hand"]
