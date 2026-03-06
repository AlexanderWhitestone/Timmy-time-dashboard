"""Integration tests for the Paperclip task runner — full green-path workflow.

Tests the complete autonomous cycle:
  1. Timmy grabs the first task in queue
  2. Timmy processes the task (muses about automation, writes recursive task)
  3. Timmy completes the task and submits a response
  4. Confirm Timmy creates a follow-up task for himself

Also tests: external task injection via Paperclip API → Timmy processes → marked done.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.paperclip.bridge import PaperclipBridge
from integrations.paperclip.client import PaperclipClient
from integrations.paperclip.models import (
    CreateIssueRequest,
    PaperclipComment,
    PaperclipIssue,
    UpdateIssueRequest,
)
from integrations.paperclip.task_runner import TaskRunner


# ── Fixtures ──────────────────────────────────────────────────────────────────

TIMMY_AGENT_ID = "agent-timmy"
COMPANY_ID = "comp-1"


@pytest.fixture
def mock_client():
    """Fully stubbed PaperclipClient with async methods."""
    client = MagicMock(spec=PaperclipClient)
    client.healthy = AsyncMock(return_value=True)
    client.list_issues = AsyncMock(return_value=[])
    client.get_issue = AsyncMock(return_value=None)
    client.create_issue = AsyncMock(return_value=None)
    client.update_issue = AsyncMock(return_value=None)
    client.delete_issue = AsyncMock(return_value=True)
    client.add_comment = AsyncMock(return_value=None)
    client.list_comments = AsyncMock(return_value=[])
    client.checkout_issue = AsyncMock(return_value={"ok": True})
    client.release_issue = AsyncMock(return_value={"ok": True})
    client.wake_agent = AsyncMock(return_value=None)
    client.list_agents = AsyncMock(return_value=[])
    client.list_goals = AsyncMock(return_value=[])
    client.create_goal = AsyncMock(return_value=None)
    client.list_approvals = AsyncMock(return_value=[])
    client.list_heartbeat_runs = AsyncMock(return_value=[])
    client.cancel_run = AsyncMock(return_value=None)
    client.approve = AsyncMock(return_value=None)
    client.reject = AsyncMock(return_value=None)
    return client


@pytest.fixture
def bridge(mock_client):
    return PaperclipBridge(client=mock_client)


@pytest.fixture
def settings_patch():
    """Patch settings for all task runner tests."""
    with patch("integrations.paperclip.task_runner.settings") as ts, \
         patch("integrations.paperclip.bridge.settings") as bs:
        for s in (ts, bs):
            s.paperclip_enabled = True
            s.paperclip_agent_id = TIMMY_AGENT_ID
            s.paperclip_company_id = COMPANY_ID
            s.paperclip_url = "http://fake:3100"
            s.paperclip_poll_interval = 0
        yield ts


def _make_issue(
    id: str = "issue-1",
    title: str = "Muse about task automation",
    description: str = "Reflect on how you handle tasks and write a recursive self-improvement task.",
    status: str = "open",
    assignee_id: str = TIMMY_AGENT_ID,
    priority: str = "normal",
    labels: list[str] | None = None,
) -> PaperclipIssue:
    return PaperclipIssue(
        id=id,
        title=title,
        description=description,
        status=status,
        assignee_id=assignee_id,
        priority=priority,
        labels=labels or [],
    )


def _make_follow_up_issue(original_id: str = "issue-1") -> PaperclipIssue:
    return PaperclipIssue(
        id="issue-2",
        title=f"Follow-up: Muse about task automation",
        description=f"Automated follow-up from completed task",
        status="open",
        assignee_id=TIMMY_AGENT_ID,
        priority="normal",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Timmy grabs the first task in queue
# ═══════════════════════════════════════════════════════════════════════════════


class TestGrabNextTask:
    """Verify Timmy picks the first open issue assigned to him."""

    async def test_grabs_first_assigned_issue(self, mock_client, bridge, settings_patch):
        """Timmy should grab the first open issue where assignee_id matches his agent ID."""
        issue = _make_issue()
        mock_client.list_issues.return_value = [issue]

        runner = TaskRunner(bridge=bridge)
        grabbed = await runner.grab_next_task()

        assert grabbed is not None
        assert grabbed.id == "issue-1"
        assert grabbed.assignee_id == TIMMY_AGENT_ID
        mock_client.list_issues.assert_awaited_once_with(status="open")

    async def test_skips_issues_not_assigned_to_timmy(self, mock_client, bridge, settings_patch):
        """Issues assigned to other agents should be skipped."""
        other_issue = _make_issue(id="other-1", assignee_id="agent-codex")
        timmy_issue = _make_issue(id="timmy-1")
        mock_client.list_issues.return_value = [other_issue, timmy_issue]

        runner = TaskRunner(bridge=bridge)
        grabbed = await runner.grab_next_task()

        assert grabbed is not None
        assert grabbed.id == "timmy-1"

    async def test_returns_none_when_queue_empty(self, mock_client, bridge, settings_patch):
        """No issues in queue → return None."""
        mock_client.list_issues.return_value = []

        runner = TaskRunner(bridge=bridge)
        grabbed = await runner.grab_next_task()

        assert grabbed is None

    async def test_returns_none_when_no_agent_id(self, mock_client, bridge, settings_patch):
        """If agent ID is not configured, cannot grab tasks."""
        settings_patch.paperclip_agent_id = ""

        runner = TaskRunner(bridge=bridge)
        grabbed = await runner.grab_next_task()

        assert grabbed is None
        mock_client.list_issues.assert_not_awaited()

    async def test_grabs_first_of_multiple_assigned(self, mock_client, bridge, settings_patch):
        """When multiple issues are assigned to Timmy, grab the first one."""
        issues = [
            _make_issue(id="first", title="First task"),
            _make_issue(id="second", title="Second task"),
            _make_issue(id="third", title="Third task"),
        ]
        mock_client.list_issues.return_value = issues

        runner = TaskRunner(bridge=bridge)
        grabbed = await runner.grab_next_task()

        assert grabbed.id == "first"


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Timmy processes the task
# ═══════════════════════════════════════════════════════════════════════════════


class TestProcessTask:
    """Verify Timmy checks out the issue and processes it."""

    async def test_checks_out_issue_before_processing(self, mock_client, bridge, settings_patch):
        """Issue must be checked out before processing begins."""
        issue = _make_issue()

        async def fake_processor(task_id, desc, ctx):
            # By the time we're called, checkout should have happened
            mock_client.checkout_issue.assert_awaited_once_with("issue-1")
            return "Mused about automation deeply"

        runner = TaskRunner(bridge=bridge, process_fn=fake_processor)
        result = await runner.process_task(issue)

        assert result == "Mused about automation deeply"

    async def test_passes_context_to_processor(self, mock_client, bridge, settings_patch):
        """The processor receives issue metadata as context."""
        issue = _make_issue(priority="high", labels=["automation", "meta"])
        captured_ctx = {}

        async def capture_processor(task_id, desc, ctx):
            captured_ctx.update(ctx)
            return "done"

        runner = TaskRunner(bridge=bridge, process_fn=capture_processor)
        await runner.process_task(issue)

        assert captured_ctx["issue_id"] == "issue-1"
        assert captured_ctx["title"] == "Muse about task automation"
        assert captured_ctx["priority"] == "high"
        assert "automation" in captured_ctx["labels"]

    async def test_default_processor_returns_message(self, mock_client, bridge, settings_patch):
        """Without a custom process_fn, a default result is returned."""
        issue = _make_issue()

        runner = TaskRunner(bridge=bridge)  # No process_fn
        result = await runner.process_task(issue)

        assert "Muse about task automation" in result


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Timmy completes the task and submits response
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompleteTask:
    """Verify Timmy posts a completion comment and marks the issue done."""

    async def test_posts_completion_comment(self, mock_client, bridge, settings_patch):
        """A [Timmy] comment should be posted with the result."""
        issue = _make_issue()
        mock_client.update_issue.return_value = PaperclipIssue(
            id="issue-1", title="Done", status="done"
        )

        runner = TaskRunner(bridge=bridge)
        ok = await runner.complete_task(issue, "I reflected on automation patterns")

        assert ok is True
        # Verify comment was posted
        mock_client.add_comment.assert_awaited_once()
        comment_args = mock_client.add_comment.call_args
        assert comment_args[0][0] == "issue-1"
        assert "[Timmy]" in comment_args[0][1]
        assert "I reflected on automation patterns" in comment_args[0][1]

    async def test_marks_issue_done(self, mock_client, bridge, settings_patch):
        """Issue status should be updated to 'done'."""
        issue = _make_issue()
        mock_client.update_issue.return_value = PaperclipIssue(
            id="issue-1", title="Done", status="done"
        )

        runner = TaskRunner(bridge=bridge)
        ok = await runner.complete_task(issue, "Result")

        assert ok is True
        mock_client.update_issue.assert_awaited_once()
        update_call = mock_client.update_issue.call_args
        assert update_call[0][0] == "issue-1"
        assert update_call[0][1].status == "done"

    async def test_returns_false_on_close_failure(self, mock_client, bridge, settings_patch):
        """If closing the issue fails, return False."""
        issue = _make_issue()
        mock_client.update_issue.return_value = None  # Failure

        runner = TaskRunner(bridge=bridge)
        ok = await runner.complete_task(issue, "Result")

        assert ok is False


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Timmy creates a follow-up task for himself
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateFollowUp:
    """Verify Timmy creates a recursive follow-up task assigned to himself."""

    async def test_creates_follow_up_assigned_to_self(self, mock_client, bridge, settings_patch):
        """Follow-up issue should be assigned to Timmy."""
        original = _make_issue()
        follow_up = _make_follow_up_issue()
        mock_client.create_issue.return_value = follow_up

        runner = TaskRunner(bridge=bridge)
        result = await runner.create_follow_up(original, "Automation musings complete")

        assert result is not None
        assert result.id == "issue-2"
        # Verify create_issue was called with correct params
        create_call = mock_client.create_issue.call_args
        req = create_call[0][0]
        assert "Follow-up" in req.title
        assert TIMMY_AGENT_ID == req.assignee_id

    async def test_follow_up_references_original(self, mock_client, bridge, settings_patch):
        """Follow-up description should reference the original task."""
        original = _make_issue(id="orig-99", title="Reflect on automation")
        mock_client.create_issue.return_value = _make_follow_up_issue("orig-99")

        runner = TaskRunner(bridge=bridge)
        await runner.create_follow_up(original, "Deep thoughts on recursion")

        create_call = mock_client.create_issue.call_args
        req = create_call[0][0]
        assert "orig-99" in req.description
        assert "Reflect on automation" in req.description
        assert "Deep thoughts on recursion" in req.description

    async def test_follow_up_preserves_priority(self, mock_client, bridge, settings_patch):
        """Follow-up should inherit the original task's priority."""
        original = _make_issue(priority="high")
        mock_client.create_issue.return_value = _make_follow_up_issue()

        runner = TaskRunner(bridge=bridge)
        await runner.create_follow_up(original, "result")

        create_call = mock_client.create_issue.call_args
        req = create_call[0][0]
        assert req.priority == "high"

    async def test_follow_up_not_woken_immediately(self, mock_client, bridge, settings_patch):
        """Follow-up should NOT wake the agent — the next poll picks it up."""
        original = _make_issue()
        mock_client.create_issue.return_value = _make_follow_up_issue()

        runner = TaskRunner(bridge=bridge)
        await runner.create_follow_up(original, "result")

        # wake_agent should NOT have been called for the follow-up
        mock_client.wake_agent.assert_not_awaited()

    async def test_returns_none_on_create_failure(self, mock_client, bridge, settings_patch):
        """If Paperclip fails to create the follow-up, return None."""
        original = _make_issue()
        mock_client.create_issue.return_value = None

        runner = TaskRunner(bridge=bridge)
        result = await runner.create_follow_up(original, "result")

        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# FULL GREEN PATH: run_once end-to-end
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunOnceGreenPath:
    """Full integration test: grab → process → complete → follow-up."""

    async def test_full_cycle_happy_path(self, mock_client, bridge, settings_patch):
        """Complete green-path: task grabbed, processed, completed, follow-up created."""
        original = _make_issue(
            title="Muse about task automation and write a recursive task",
            description="Reflect on your task processing. Create a follow-up for yourself.",
        )
        follow_up = _make_follow_up_issue()

        # Wire up mock responses
        mock_client.list_issues.return_value = [original]
        mock_client.update_issue.return_value = PaperclipIssue(
            id="issue-1", title="Done", status="done"
        )
        mock_client.create_issue.return_value = follow_up

        async def musing_processor(task_id, desc, ctx):
            return (
                "I've reflected on my task automation patterns. "
                "The recursive loop of grab-process-complete-followup "
                "ensures continuous self-improvement."
            )

        runner = TaskRunner(bridge=bridge, process_fn=musing_processor)
        summary = await runner.run_once()

        # Verify full cycle completed
        assert summary is not None
        assert summary["original_issue_id"] == "issue-1"
        assert summary["completed"] is True
        assert summary["follow_up_issue_id"] == "issue-2"
        assert "self-improvement" in summary["result"]

        # Verify ordering: list → checkout → comment → close → create follow-up
        mock_client.list_issues.assert_awaited_once()
        mock_client.checkout_issue.assert_awaited_once_with("issue-1")
        mock_client.add_comment.assert_awaited_once()
        mock_client.update_issue.assert_awaited_once()
        assert mock_client.create_issue.await_count == 1

    async def test_full_cycle_no_tasks(self, mock_client, bridge, settings_patch):
        """When no tasks in queue, run_once returns None gracefully."""
        mock_client.list_issues.return_value = []

        runner = TaskRunner(bridge=bridge)
        summary = await runner.run_once()

        assert summary is None
        mock_client.checkout_issue.assert_not_awaited()

    async def test_full_cycle_with_close_failure(self, mock_client, bridge, settings_patch):
        """If closing fails, summary reflects it but follow-up still created."""
        original = _make_issue()
        follow_up = _make_follow_up_issue()

        mock_client.list_issues.return_value = [original]
        mock_client.update_issue.return_value = None  # Close fails
        mock_client.create_issue.return_value = follow_up

        runner = TaskRunner(bridge=bridge)
        summary = await runner.run_once()

        assert summary is not None
        assert summary["completed"] is False
        assert summary["follow_up_issue_id"] == "issue-2"


# ═══════════════════════════════════════════════════════════════════════════════
# EXTERNAL INJECTION: Task added via Paperclip API, Timmy picks it up
# ═══════════════════════════════════════════════════════════════════════════════


class TestExternalTaskInjection:
    """Simulate: someone adds a task via Paperclip API → Timmy processes it."""

    async def test_externally_created_task_picked_up(self, mock_client, bridge, settings_patch):
        """A task created outside Timmy (via API) with Timmy's agent ID
        should be picked up and completed on the next run_once cycle."""
        # External system creates a task assigned to Timmy
        external_task = _make_issue(
            id="ext-task-1",
            title="Review quarterly metrics",
            description="Analyze Q1 metrics and prepare summary.",
            assignee_id=TIMMY_AGENT_ID,
        )
        follow_up = PaperclipIssue(
            id="ext-follow-1",
            title="Follow-up: Review quarterly metrics",
            status="open",
            assignee_id=TIMMY_AGENT_ID,
        )

        mock_client.list_issues.return_value = [external_task]
        mock_client.update_issue.return_value = PaperclipIssue(
            id="ext-task-1", title="Review quarterly metrics", status="done"
        )
        mock_client.create_issue.return_value = follow_up

        async def review_processor(task_id, desc, ctx):
            return "Q1 metrics reviewed. Revenue up 12%, user growth steady."

        runner = TaskRunner(bridge=bridge, process_fn=review_processor)
        summary = await runner.run_once()

        # External task was processed
        assert summary is not None
        assert summary["original_issue_id"] == "ext-task-1"
        assert summary["completed"] is True
        assert "Revenue up 12%" in summary["result"]

        # Follow-up was created
        assert summary["follow_up_issue_id"] == "ext-follow-1"

    async def test_external_task_among_others(self, mock_client, bridge, settings_patch):
        """Timmy ignores tasks assigned to others, grabs only his own."""
        other_task = _make_issue(id="other-1", assignee_id="agent-codex", title="Codex work")
        timmy_task = _make_issue(id="timmy-ext", title="Timmy's external task")

        mock_client.list_issues.return_value = [other_task, timmy_task]
        mock_client.update_issue.return_value = PaperclipIssue(
            id="timmy-ext", title="Done", status="done"
        )
        mock_client.create_issue.return_value = _make_follow_up_issue()

        runner = TaskRunner(bridge=bridge)
        summary = await runner.run_once()

        assert summary["original_issue_id"] == "timmy-ext"
        mock_client.checkout_issue.assert_awaited_once_with("timmy-ext")


# ═══════════════════════════════════════════════════════════════════════════════
# RECURSIVE CHAIN: follow-up picked up on subsequent cycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecursiveTaskChain:
    """Verify the follow-up from cycle 1 is picked up in cycle 2."""

    async def test_follow_up_becomes_next_task(self, mock_client, bridge, settings_patch):
        """Cycle 1 creates follow-up → Cycle 2 grabs that follow-up."""
        # Cycle 1: original task
        original = _make_issue(id="task-A", title="Initial musing")
        follow_up_1 = PaperclipIssue(
            id="task-B",
            title="Follow-up: Initial musing",
            description="Continue the work",
            status="open",
            assignee_id=TIMMY_AGENT_ID,
            priority="normal",
        )
        follow_up_2 = PaperclipIssue(
            id="task-C",
            title="Follow-up: Follow-up: Initial musing",
            status="open",
            assignee_id=TIMMY_AGENT_ID,
        )

        # Cycle 1 setup
        mock_client.list_issues.return_value = [original]
        mock_client.update_issue.return_value = PaperclipIssue(
            id="task-A", title="Done", status="done"
        )
        mock_client.create_issue.return_value = follow_up_1

        runner = TaskRunner(bridge=bridge)
        summary_1 = await runner.run_once()

        assert summary_1["original_issue_id"] == "task-A"
        assert summary_1["follow_up_issue_id"] == "task-B"

        # Cycle 2: follow-up is now the next task
        mock_client.list_issues.return_value = [follow_up_1]
        mock_client.update_issue.return_value = PaperclipIssue(
            id="task-B", title="Done", status="done"
        )
        mock_client.create_issue.return_value = follow_up_2

        summary_2 = await runner.run_once()

        assert summary_2["original_issue_id"] == "task-B"
        assert summary_2["follow_up_issue_id"] == "task-C"

    async def test_three_cycle_chain(self, mock_client, bridge, settings_patch):
        """Three consecutive cycles form a recursive chain."""
        tasks = [
            _make_issue(id=f"chain-{i}", title=f"Chain task {i}")
            for i in range(3)
        ]
        follow_ups = [
            PaperclipIssue(
                id=f"chain-{i + 1}",
                title=f"Follow-up: Chain task {i}",
                status="open",
                assignee_id=TIMMY_AGENT_ID,
            )
            for i in range(3)
        ]

        runner = TaskRunner(bridge=bridge)
        completed_ids = []

        for i in range(3):
            mock_client.list_issues.return_value = [tasks[i]]
            mock_client.update_issue.return_value = PaperclipIssue(
                id=tasks[i].id, title="Done", status="done"
            )
            mock_client.create_issue.return_value = follow_ups[i]

            summary = await runner.run_once()
            assert summary is not None
            completed_ids.append(summary["original_issue_id"])

        assert completed_ids == ["chain-0", "chain-1", "chain-2"]


# ═══════════════════════════════════════════════════════════════════════════════
# STOP SIGNAL: runner loop respects stop()
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunnerLifecycle:
    """Verify start/stop behavior."""

    async def test_stop_halts_loop(self, mock_client, bridge, settings_patch):
        """Calling stop() should prevent further iterations."""
        runner = TaskRunner(bridge=bridge)
        runner._running = True
        runner.stop()
        assert runner._running is False

    async def test_start_disabled_when_interval_zero(self, mock_client, bridge, settings_patch):
        """start() returns immediately if poll_interval <= 0."""
        settings_patch.paperclip_poll_interval = 0

        runner = TaskRunner(bridge=bridge)
        # Should return immediately without entering loop
        await runner.start()

        mock_client.list_issues.assert_not_awaited()
