"""Functional test: Timmy reaches inbox zero by processing all queued tasks.

Verifies that when tasks are created in the queue, the TaskProcessor
picks them up one by one and drives them all to COMPLETED (or FAILED),
leaving zero pending/approved/running tasks — inbox zero.
"""

import asyncio

import pytest

from swarm.task_processor import TaskProcessor
from swarm.task_queue.models import (
    TaskStatus,
    create_task,
    get_task,
    get_counts_by_status,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _pending_or_active_count() -> int:
    """Count tasks that are NOT in a terminal state."""
    counts = get_counts_by_status()
    terminal = counts.get("completed", 0) + counts.get("failed", 0) + counts.get("vetoed", 0)
    total = sum(counts.values())
    return total - terminal


def _make_processor() -> TaskProcessor:
    """Create a TaskProcessor with simple echo handlers."""
    proc = TaskProcessor("timmy")
    proc.register_handler("chat_response", lambda t: f"Done: {t.title}")
    proc.register_handler("thought", lambda t: f"Thought: {t.title}")
    proc.register_handler("internal", lambda t: f"Internal: {t.title}")
    return proc


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("isolated_task_db")
class TestInboxZero:
    """Timmy should drain his task queue to zero pending items."""

    async def test_single_task_completes(self):
        """A single approved task gets picked up and completed."""
        proc = _make_processor()

        task = create_task(
            title="Say hello",
            description="Greet the user",
            task_type="chat_response",
            assigned_to="timmy",
            created_by="user",
            auto_approve=True,
        )

        result = await proc.process_next_task()
        assert result is not None, "Processor should have picked up the task"

        finished = get_task(task.id)
        assert finished.status == TaskStatus.COMPLETED
        assert finished.result == "Done: Say hello"
        assert finished.completed_at is not None

    async def test_multiple_tasks_all_complete(self):
        """Multiple tasks are processed one-by-one until inbox is empty."""
        proc = _make_processor()

        titles = ["Fix login bug", "Write docs", "Refactor auth", "Deploy v2", "Update deps"]
        for title in titles:
            create_task(
                title=title,
                task_type="chat_response",
                assigned_to="timmy",
                auto_approve=True,
            )

        assert _pending_or_active_count() == len(titles)

        processed = 0
        for _ in range(len(titles) + 5):
            result = await proc.process_next_task()
            if result is None:
                break
            processed += 1

        assert processed == len(titles), f"Expected {len(titles)} processed, got {processed}"
        assert _pending_or_active_count() == 0, "Inbox is NOT zero"

    async def test_mixed_task_types_all_complete(self):
        """Different task types (chat, thought, internal) all get handled."""
        proc = _make_processor()

        t1 = create_task(title="Chat task", task_type="chat_response", assigned_to="timmy", auto_approve=True)
        t2 = create_task(title="Thought task", task_type="thought", assigned_to="timmy", auto_approve=True)
        t3 = create_task(title="Internal task", task_type="internal", assigned_to="timmy", auto_approve=True)

        for _ in range(10):
            result = await proc.process_next_task()
            if result is None:
                break

        assert _pending_or_active_count() == 0, "Not all task types were handled"
        assert get_task(t1.id).result == "Done: Chat task"
        assert get_task(t2.id).result == "Thought: Thought task"
        assert get_task(t3.id).result == "Internal: Internal task"

    async def test_priority_ordering(self):
        """Urgent tasks are processed before normal ones."""
        proc = _make_processor()

        create_task(title="Normal task", task_type="chat_response", assigned_to="timmy", priority="normal", auto_approve=True)
        create_task(title="Urgent task", task_type="chat_response", assigned_to="timmy", priority="urgent", auto_approve=True)
        create_task(title="Low task", task_type="chat_response", assigned_to="timmy", priority="low", auto_approve=True)

        order = []
        for _ in range(10):
            result = await proc.process_next_task()
            if result is None:
                break
            order.append(result.title)

        assert order == ["Urgent task", "Normal task", "Low task"]
        assert _pending_or_active_count() == 0

    async def test_failing_task_does_not_block_queue(self):
        """A task whose handler raises still gets marked FAILED and the queue moves on."""
        proc = TaskProcessor("timmy")

        def exploding_handler(task):
            raise RuntimeError("Kaboom!")

        proc.register_handler("chat_response", exploding_handler)
        proc.register_handler("thought", lambda t: "OK")

        t_fail = create_task(title="Will fail", task_type="chat_response", assigned_to="timmy", auto_approve=True)
        t_ok = create_task(title="Will succeed", task_type="thought", assigned_to="timmy", auto_approve=True)

        # Process first task — handler raises, processor marks FAILED and re-raises
        with pytest.raises(RuntimeError, match="Kaboom"):
            await proc.process_next_task()

        assert get_task(t_fail.id).status == TaskStatus.FAILED

        # Process second task — should succeed despite the prior failure
        result = await proc.process_next_task()
        assert result is not None
        assert result.title == "Will succeed"
        assert get_task(t_ok.id).status == TaskStatus.COMPLETED
        assert _pending_or_active_count() == 0

    async def test_unregistered_type_still_completes(self):
        """A task with no registered handler still completes (with a diagnostic message)."""
        proc = TaskProcessor("timmy")
        # No handlers registered at all

        task = create_task(title="Mystery task", task_type="unknown_type", assigned_to="timmy", auto_approve=True)

        result = await proc.process_next_task()
        assert result is not None, "Task with no handler should still be processed"

        finished = get_task(task.id)
        assert finished.status == TaskStatus.COMPLETED
        assert "No handler" in finished.result

    async def test_pending_approval_tasks_are_picked_up(self):
        """Tasks in pending_approval state are also picked up by the processor.

        This is by design — get_next_pending_task queries both 'approved' and
        'pending_approval' so the processor can work without human gates.
        """
        proc = _make_processor()

        task = create_task(
            title="Needs approval",
            task_type="chat_response",
            assigned_to="timmy",
            auto_approve=False,
        )
        assert task.status == TaskStatus.PENDING_APPROVAL

        result = await proc.process_next_task()
        assert result is not None

        finished = get_task(task.id)
        assert finished.status == TaskStatus.COMPLETED

    async def test_run_loop_reaches_inbox_zero(self):
        """The processing loop drains all tasks within a bounded time."""
        proc = _make_processor()

        for i in range(7):
            create_task(
                title=f"Loop task {i}",
                task_type="chat_response",
                assigned_to="timmy",
                auto_approve=True,
            )

        assert _pending_or_active_count() == 7

        async def run_briefly():
            for _ in range(20):
                try:
                    await proc.process_next_task()
                except Exception:
                    pass
                if _pending_or_active_count() == 0:
                    return
                await asyncio.sleep(0.01)

        await asyncio.wait_for(run_briefly(), timeout=5.0)
        assert _pending_or_active_count() == 0, "Loop did not reach inbox zero"

    async def test_timestamps_set_on_completion(self):
        """started_at and completed_at are properly set during processing."""
        proc = _make_processor()

        task = create_task(
            title="Timestamp check",
            task_type="chat_response",
            assigned_to="timmy",
            auto_approve=True,
        )
        assert task.started_at is None
        assert task.completed_at is None

        await proc.process_next_task()

        finished = get_task(task.id)
        assert finished.started_at is not None, "started_at should be set when task runs"
        assert finished.completed_at is not None, "completed_at should be set when task finishes"
        assert finished.started_at <= finished.completed_at

    async def test_steps_updated_on_completion(self):
        """Task steps are updated as the processor works through a task."""
        proc = _make_processor()

        task = create_task(
            title="Steps check",
            task_type="chat_response",
            assigned_to="timmy",
            auto_approve=True,
        )

        await proc.process_next_task()

        finished = get_task(task.id)
        assert finished.status == TaskStatus.COMPLETED
        assert len(finished.steps) > 0
        assert finished.steps[0]["status"] == "completed"

    async def test_inbox_zero_after_burst(self):
        """Simulate a burst of 20 tasks and verify inbox zero is achieved."""
        proc = _make_processor()

        task_ids = []
        for i in range(20):
            t = create_task(
                title=f"Burst task {i}",
                task_type="chat_response",
                assigned_to="timmy",
                auto_approve=True,
            )
            task_ids.append(t.id)

        assert _pending_or_active_count() == 20

        processed = 0
        for _ in range(30):
            result = await proc.process_next_task()
            if result is None:
                break
            processed += 1

        assert processed == 20
        assert _pending_or_active_count() == 0, f"Inbox NOT zero — {_pending_or_active_count()} remaining"

        # All 20 should be completed
        completed = [get_task(tid) for tid in task_ids]
        assert all(t.status == TaskStatus.COMPLETED for t in completed)
