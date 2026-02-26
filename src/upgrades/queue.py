"""Upgrade Queue management - bridges self-modify loop with approval workflow."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from upgrades.models import (
    Upgrade,
    UpgradeStatus,
    create_upgrade,
    get_upgrade,
    approve_upgrade,
    reject_upgrade,
    mark_applied,
    mark_failed,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent


class UpgradeQueue:
    """Manages the upgrade approval and application workflow."""
    
    @staticmethod
    def propose(
        branch_name: str,
        description: str,
        files_changed: list[str],
        diff_preview: str,
        test_passed: bool = False,
        test_output: str = "",
    ) -> Upgrade:
        """Propose a new upgrade for approval.
        
        This is called by the self-modify loop when it generates changes.
        The upgrade is created in 'proposed' state and waits for human approval.
        
        Args:
            branch_name: Git branch with the changes
            description: What the upgrade does
            files_changed: List of modified files
            diff_preview: Short diff for review
            test_passed: Whether tests passed
            test_output: Test output
        
        Returns:
            The created Upgrade proposal
        """
        upgrade = create_upgrade(
            branch_name=branch_name,
            description=description,
            files_changed=files_changed,
            diff_preview=diff_preview,
            test_passed=test_passed,
            test_output=test_output,
        )
        
        logger.info(
            "Upgrade proposed: %s (%s) - %d files",
            upgrade.id[:8],
            branch_name,
            len(files_changed),
        )
        
        # Log to event log
        try:
            from swarm.event_log import log_event, EventType
            log_event(
                EventType.SYSTEM_INFO,
                source="upgrade_queue",
                data={
                    "upgrade_id": upgrade.id,
                    "branch": branch_name,
                    "description": description,
                    "test_passed": test_passed,
                },
            )
        except Exception:
            pass
        
        return upgrade
    
    @staticmethod
    def approve(upgrade_id: str, approved_by: str = "dashboard") -> Optional[Upgrade]:
        """Approve an upgrade proposal.
        
        Called from dashboard when user clicks "Approve".
        Does NOT apply the upgrade - that happens separately.
        
        Args:
            upgrade_id: The upgrade to approve
            approved_by: Who approved it (for audit)
        
        Returns:
            Updated Upgrade or None if not found/not in proposed state
        """
        upgrade = approve_upgrade(upgrade_id, approved_by)
        
        if upgrade:
            logger.info("Upgrade approved: %s by %s", upgrade_id[:8], approved_by)
        
        return upgrade
    
    @staticmethod
    def reject(upgrade_id: str) -> Optional[Upgrade]:
        """Reject an upgrade proposal.
        
        Called from dashboard when user clicks "Reject".
        Cleans up the branch.
        
        Args:
            upgrade_id: The upgrade to reject
        
        Returns:
            Updated Upgrade or None
        """
        upgrade = reject_upgrade(upgrade_id)
        
        if upgrade:
            logger.info("Upgrade rejected: %s", upgrade_id[:8])
            
            # Clean up branch
            try:
                subprocess.run(
                    ["git", "branch", "-D", upgrade.branch_name],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    check=False,
                )
            except Exception as exc:
                logger.warning("Failed to delete branch %s: %s", upgrade.branch_name, exc)
        
        return upgrade
    
    @staticmethod
    def apply(upgrade_id: str) -> tuple[bool, str]:
        """Apply an approved upgrade.
        
        This is the critical operation that actually modifies the codebase:
        1. Checks out the branch
        2. Runs tests
        3. If tests pass: merges to main
        4. Updates upgrade status
        
        Args:
            upgrade_id: The approved upgrade to apply
        
        Returns:
            (success, message) tuple
        """
        upgrade = get_upgrade(upgrade_id)
        
        if not upgrade:
            return False, "Upgrade not found"
        
        if upgrade.status != UpgradeStatus.APPROVED:
            return False, f"Upgrade not approved (status: {upgrade.status.value})"
        
        logger.info("Applying upgrade: %s (%s)", upgrade_id[:8], upgrade.branch_name)
        
        try:
            # 1. Checkout branch
            result = subprocess.run(
                ["git", "checkout", upgrade.branch_name],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                mark_failed(upgrade_id, f"Checkout failed: {result.stderr}")
                return False, f"Failed to checkout branch: {result.stderr}"
            
            # 2. Run tests
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-x", "-q"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            if result.returncode != 0:
                mark_failed(upgrade_id, f"Tests failed: {result.stdout}\n{result.stderr}")
                # Switch back to main
                subprocess.run(["git", "checkout", "main"], cwd=PROJECT_ROOT, check=False)
                return False, "Tests failed"
            
            # 3. Merge to main
            result = subprocess.run(
                ["git", "checkout", "main"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                mark_failed(upgrade_id, f"Failed to checkout main: {result.stderr}")
                return False, "Failed to checkout main"
            
            result = subprocess.run(
                ["git", "merge", "--no-ff", upgrade.branch_name, "-m", f"Apply upgrade: {upgrade.description}"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                mark_failed(upgrade_id, f"Merge failed: {result.stderr}")
                return False, "Merge failed"
            
            # 4. Mark as applied
            mark_applied(upgrade_id)
            
            # 5. Clean up branch
            subprocess.run(
                ["git", "branch", "-d", upgrade.branch_name],
                cwd=PROJECT_ROOT,
                capture_output=True,
                check=False,
            )
            
            logger.info("Upgrade applied successfully: %s", upgrade_id[:8])
            return True, "Upgrade applied successfully"
            
        except subprocess.TimeoutExpired:
            mark_failed(upgrade_id, "Tests timed out")
            subprocess.run(["git", "checkout", "main"], cwd=PROJECT_ROOT, check=False)
            return False, "Tests timed out"
            
        except Exception as exc:
            error_msg = str(exc)
            mark_failed(upgrade_id, error_msg)
            subprocess.run(["git", "checkout", "main"], cwd=PROJECT_ROOT, check=False)
            return False, f"Error: {error_msg}"
    
    @staticmethod
    def get_full_diff(upgrade_id: str) -> str:
        """Get full git diff for an upgrade.
        
        Args:
            upgrade_id: The upgrade to get diff for
        
        Returns:
            Git diff output
        """
        upgrade = get_upgrade(upgrade_id)
        if not upgrade:
            return "Upgrade not found"
        
        try:
            result = subprocess.run(
                ["git", "diff", "main..." + upgrade.branch_name],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as exc:
            return f"Error getting diff: {exc}"


# Convenience functions for self-modify loop
def propose_upgrade_from_loop(
    branch_name: str,
    description: str,
    files_changed: list[str],
    diff: str,
    test_output: str = "",
) -> Upgrade:
    """Called by self-modify loop to propose an upgrade.
    
    Tests are expected to have been run by the loop before calling this.
    """
    # Check if tests passed from output
    test_passed = "passed" in test_output.lower() or " PASSED " in test_output
    
    return UpgradeQueue.propose(
        branch_name=branch_name,
        description=description,
        files_changed=files_changed,
        diff_preview=diff[:2000],  # First 2000 chars
        test_passed=test_passed,
        test_output=test_output,
    )
