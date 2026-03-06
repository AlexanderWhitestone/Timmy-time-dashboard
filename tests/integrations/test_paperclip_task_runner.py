"""Integration tests for the Paperclip task runner — full green-path workflow.

Tests the complete autonomous cycle with a StubOrchestrator that exercises
the real pipe (TaskRunner → orchestrator.execute_task → bridge → client)
while stubbing only the LLM intelligence layer.

Green path:
  1. Timmy grabs first task in queue
  2. Orchestrator.execute_task processes it (stub returns input-aware response)
  3. Timmy posts completion comment and marks issue done
  4. Timmy creates a recursive follow-up task for himself

The stub is deliberately input-aware — it echoes back task metadata so
assertions can prove data actually flowed through the pipe, not just that
methods were called.

Live-LLM tests (``@pytest.mark.ollama``) are at the bottom; they hit a real
tiny model via Ollama and are skipped when Ollama is not running.
Run them with: ``tox -e ollama`` or ``pytest -m ollama``
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.paperclip.bridge import PaperclipBridge
from integrations.paperclip.client import PaperclipClient
from integrations.paperclip.models import (
    PaperclipIssue,
)
from integrations.paperclip.task_runner import TaskRunner


# ── Constants ─────────────────────────────────────────────────────────────────

TIMMY_AGENT_ID = "agent-timmy"
COMPANY_ID = "comp-1"


# ── StubOrchestrator: exercises the pipe, stubs the intelligence ──────────────


class StubOrchestrator:
    """Deterministic orchestrator that proves data flows through the pipe.

    Returns responses that reference input metadata — so tests can assert
    the pipe actually connected (task_id, title, priority all appear in output).
    Tracks every call for post-hoc inspection.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute_task(
        self, task_id: str, description: str, context: dict
    ) -> dict:
        call_record = {
            "task_id": task_id,
            "description": description,
            "context": dict(context),
        }
        self.calls.append(call_record)

        title = context.get("title", description[:50])
        priority = context.get("priority", "normal")

        return {
            "task_id": task_id,
            "agent": "orchestrator",
            "result": (
                f"[Orchestrator] Processed '{title}'. "
                f"Task {task_id} handled with priority {priority}. "
                "Self-reflection: my task automation loop is functioning. "
                "I should create a follow-up to review this pattern."
            ),
            "status": "completed",
        }


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def stub_orchestrator():
    return StubOrchestrator()


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


# ── Helpers ───────────────────────────────────────────────────────────────────


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


def _make_done(id: str = "issue-1", title: str = "Done") -> PaperclipIssue:
    return PaperclipIssue(id=id, title=title, status="done")


def _make_follow_up(id: str = "issue-2") -> PaperclipIssue:
    return PaperclipIssue(
        id=id,
        title="Follow-up: Muse about task automation",
        description="Automated follow-up from completed task",
        status="open",
        assignee_id=TIMMY_AGENT_ID,
        priority="normal",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PIPE WIRING: verify orchestrator is actually connected
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorWiring:
    """Verify the orchestrator parameter actually connects to the pipe."""

    async def test_orchestrator_execute_task_is_called(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """When orchestrator is wired, process_task calls execute_task."""
        issue = _make_issue()

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        result = await runner.process_task(issue)

        assert len(stub_orchestrator.calls) == 1
        call = stub_orchestrator.calls[0]
        assert call["task_id"] == "issue-1"
        assert call["context"]["title"] == "Muse about task automation"

    async def test_orchestrator_receives_full_context(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """Context dict passed to execute_task includes all issue metadata."""
        issue = _make_issue(
            id="ctx-test",
            title="Context verification",
            priority="high",
            labels=["automation", "meta"],
        )

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        await runner.process_task(issue)

        ctx = stub_orchestrator.calls[0]["context"]
        assert ctx["issue_id"] == "ctx-test"
        assert ctx["title"] == "Context verification"
        assert ctx["priority"] == "high"
        assert ctx["labels"] == ["automation", "meta"]

    async def test_orchestrator_dict_result_unwrapped(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """When execute_task returns a dict, the 'result' key is extracted."""
        issue = _make_issue()

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        result = await runner.process_task(issue)

        # StubOrchestrator returns dict with "result" key
        assert "[Orchestrator]" in result
        assert "issue-1" in result

    async def test_orchestrator_string_result_passthrough(
        self, mock_client, bridge, settings_patch,
    ):
        """When execute_task returns a plain string, it passes through."""

        class StringOrchestrator:
            async def execute_task(self, task_id, description, context):
                return f"Plain string result for {task_id}"

        runner = TaskRunner(bridge=bridge, orchestrator=StringOrchestrator())
        result = await runner.process_task(_make_issue())

        assert result == "Plain string result for issue-1"

    async def test_process_fn_overrides_orchestrator(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """Explicit process_fn takes priority over orchestrator."""

        async def override(task_id, desc, ctx):
            return "override wins"

        runner = TaskRunner(
            bridge=bridge, orchestrator=stub_orchestrator, process_fn=override,
        )
        result = await runner.process_task(_make_issue())

        assert result == "override wins"
        assert len(stub_orchestrator.calls) == 0  # orchestrator NOT called


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Timmy grabs the first task in queue
# ═══════════════════════════════════════════════════════════════════════════════


class TestGrabNextTask:
    """Verify Timmy picks the first open issue assigned to him."""

    async def test_grabs_first_assigned_issue(self, mock_client, bridge, settings_patch):
        issue = _make_issue()
        mock_client.list_issues.return_value = [issue]

        runner = TaskRunner(bridge=bridge)
        grabbed = await runner.grab_next_task()

        assert grabbed is not None
        assert grabbed.id == "issue-1"
        assert grabbed.assignee_id == TIMMY_AGENT_ID
        mock_client.list_issues.assert_awaited_once_with(status="open")

    async def test_skips_issues_not_assigned_to_timmy(self, mock_client, bridge, settings_patch):
        other = _make_issue(id="other-1", assignee_id="agent-codex")
        mine = _make_issue(id="timmy-1")
        mock_client.list_issues.return_value = [other, mine]

        runner = TaskRunner(bridge=bridge)
        grabbed = await runner.grab_next_task()

        assert grabbed.id == "timmy-1"

    async def test_returns_none_when_queue_empty(self, mock_client, bridge, settings_patch):
        mock_client.list_issues.return_value = []
        runner = TaskRunner(bridge=bridge)
        assert await runner.grab_next_task() is None

    async def test_returns_none_when_no_agent_id(self, mock_client, bridge, settings_patch):
        settings_patch.paperclip_agent_id = ""
        runner = TaskRunner(bridge=bridge)
        assert await runner.grab_next_task() is None
        mock_client.list_issues.assert_not_awaited()

    async def test_grabs_first_of_multiple(self, mock_client, bridge, settings_patch):
        issues = [_make_issue(id=f"t-{i}", title=f"Task {i}") for i in range(3)]
        mock_client.list_issues.return_value = issues

        runner = TaskRunner(bridge=bridge)
        assert (await runner.grab_next_task()).id == "t-0"


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Timmy processes the task through the orchestrator
# ═══════════════════════════════════════════════════════════════════════════════


class TestProcessTask:
    """Verify checkout + orchestrator invocation + result flow."""

    async def test_checkout_before_orchestrator(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """Issue must be checked out before orchestrator runs."""
        issue = _make_issue()
        checkout_happened = {"before_execute": False}

        original_execute = stub_orchestrator.execute_task

        async def tracking_execute(task_id, desc, ctx):
            checkout_happened["before_execute"] = (
                mock_client.checkout_issue.await_count > 0
            )
            return await original_execute(task_id, desc, ctx)

        stub_orchestrator.execute_task = tracking_execute

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        await runner.process_task(issue)

        assert checkout_happened["before_execute"], "checkout must happen before execute_task"

    async def test_orchestrator_output_flows_to_result(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """The string returned by process_task comes from the orchestrator."""
        issue = _make_issue(id="flow-1", title="Flow verification", priority="high")

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        result = await runner.process_task(issue)

        # Verify orchestrator's output arrived — it references the input
        assert "Flow verification" in result
        assert "flow-1" in result
        assert "high" in result

    async def test_default_fallback_without_orchestrator(
        self, mock_client, bridge, settings_patch,
    ):
        """Without orchestrator or process_fn, a default message is returned."""
        issue = _make_issue(title="Fallback test")
        runner = TaskRunner(bridge=bridge)  # no orchestrator
        result = await runner.process_task(issue)
        assert "Fallback test" in result


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Timmy completes the task — comment + close
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompleteTask:
    """Verify orchestrator output flows into the completion comment."""

    async def test_orchestrator_output_in_comment(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """The comment posted to Paperclip contains the orchestrator's output."""
        issue = _make_issue(id="cmt-1", title="Comment pipe test")
        mock_client.update_issue.return_value = _make_done("cmt-1")

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        # Process to get orchestrator output
        result = await runner.process_task(issue)
        # Complete to post it as comment
        await runner.complete_task(issue, result)

        comment_content = mock_client.add_comment.call_args[0][1]
        assert "[Timmy]" in comment_content
        assert "[Orchestrator]" in comment_content
        assert "Comment pipe test" in comment_content

    async def test_marks_issue_done(
        self, mock_client, bridge, settings_patch,
    ):
        issue = _make_issue()
        mock_client.update_issue.return_value = _make_done()

        runner = TaskRunner(bridge=bridge)
        ok = await runner.complete_task(issue, "any result")

        assert ok is True
        update_req = mock_client.update_issue.call_args[0][1]
        assert update_req.status == "done"

    async def test_returns_false_on_close_failure(
        self, mock_client, bridge, settings_patch,
    ):
        mock_client.update_issue.return_value = None
        runner = TaskRunner(bridge=bridge)
        assert await runner.complete_task(_make_issue(), "result") is False


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Follow-up creation with orchestrator output embedded
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateFollowUp:
    """Verify orchestrator output flows into the follow-up description."""

    async def test_follow_up_contains_orchestrator_output(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """The follow-up description includes the orchestrator's result text."""
        issue = _make_issue(id="fu-1", title="Follow-up pipe test")
        mock_client.create_issue.return_value = _make_follow_up()

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        result = await runner.process_task(issue)
        await runner.create_follow_up(issue, result)

        create_req = mock_client.create_issue.call_args[0][0]
        # Orchestrator output should be embedded in description
        assert "[Orchestrator]" in create_req.description
        assert "fu-1" in create_req.description

    async def test_follow_up_assigned_to_self(
        self, mock_client, bridge, settings_patch,
    ):
        mock_client.create_issue.return_value = _make_follow_up()
        runner = TaskRunner(bridge=bridge)
        await runner.create_follow_up(_make_issue(), "result")

        req = mock_client.create_issue.call_args[0][0]
        assert req.assignee_id == TIMMY_AGENT_ID

    async def test_follow_up_preserves_priority(
        self, mock_client, bridge, settings_patch,
    ):
        mock_client.create_issue.return_value = _make_follow_up()
        runner = TaskRunner(bridge=bridge)
        await runner.create_follow_up(_make_issue(priority="high"), "result")

        req = mock_client.create_issue.call_args[0][0]
        assert req.priority == "high"

    async def test_follow_up_not_woken(self, mock_client, bridge, settings_patch):
        mock_client.create_issue.return_value = _make_follow_up()
        runner = TaskRunner(bridge=bridge)
        await runner.create_follow_up(_make_issue(), "result")
        mock_client.wake_agent.assert_not_awaited()

    async def test_returns_none_on_failure(self, mock_client, bridge, settings_patch):
        mock_client.create_issue.return_value = None
        runner = TaskRunner(bridge=bridge)
        assert await runner.create_follow_up(_make_issue(), "r") is None


# ═══════════════════════════════════════════════════════════════════════════════
# FULL GREEN PATH: orchestrator wired end-to-end
# ═══════════════════════════════════════════════════════════════════════════════


class TestGreenPathWithOrchestrator:
    """Full pipe: TaskRunner → StubOrchestrator → bridge → mock_client.

    Proves orchestrator output propagates to every downstream artefact:
    the comment, the follow-up description, and the summary dict.
    """

    async def test_full_cycle_orchestrator_output_everywhere(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """Orchestrator result appears in comment, follow-up, and summary."""
        original = _make_issue(
            id="green-1",
            title="Muse about task automation and write a recursive task",
            description="Reflect on your task processing. Create a follow-up.",
            priority="high",
        )
        mock_client.list_issues.return_value = [original]
        mock_client.update_issue.return_value = _make_done("green-1")
        mock_client.create_issue.return_value = _make_follow_up("green-fu")

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        summary = await runner.run_once()

        # ── Orchestrator was called with correct data
        assert len(stub_orchestrator.calls) == 1
        call = stub_orchestrator.calls[0]
        assert call["task_id"] == "green-1"
        assert call["context"]["priority"] == "high"
        assert "Reflect on your task processing" in call["description"]

        # ── Summary contains orchestrator output
        assert summary is not None
        assert summary["original_issue_id"] == "green-1"
        assert summary["completed"] is True
        assert summary["follow_up_issue_id"] == "green-fu"
        assert "[Orchestrator]" in summary["result"]
        assert "green-1" in summary["result"]

        # ── Comment posted contains orchestrator output
        comment_content = mock_client.add_comment.call_args[0][1]
        assert "[Timmy]" in comment_content
        assert "[Orchestrator]" in comment_content
        assert "high" in comment_content  # priority flowed through

        # ── Follow-up description contains orchestrator output
        follow_up_req = mock_client.create_issue.call_args[0][0]
        assert "[Orchestrator]" in follow_up_req.description
        assert "green-1" in follow_up_req.description
        assert follow_up_req.priority == "high"
        assert follow_up_req.assignee_id == TIMMY_AGENT_ID

        # ── Correct ordering of API calls
        mock_client.list_issues.assert_awaited_once()
        mock_client.checkout_issue.assert_awaited_once_with("green-1")
        mock_client.add_comment.assert_awaited_once()
        mock_client.update_issue.assert_awaited_once()
        assert mock_client.create_issue.await_count == 1

    async def test_no_tasks_returns_none(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        mock_client.list_issues.return_value = []
        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        assert await runner.run_once() is None
        assert len(stub_orchestrator.calls) == 0

    async def test_close_failure_still_creates_follow_up(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        mock_client.list_issues.return_value = [_make_issue()]
        mock_client.update_issue.return_value = None  # close fails
        mock_client.create_issue.return_value = _make_follow_up()

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        summary = await runner.run_once()

        assert summary["completed"] is False
        assert summary["follow_up_issue_id"] == "issue-2"
        assert len(stub_orchestrator.calls) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# EXTERNAL INJECTION: task from Paperclip API → orchestrator processes it
# ═══════════════════════════════════════════════════════════════════════════════


class TestExternalTaskInjection:
    """External system creates a task → Timmy's orchestrator processes it."""

    async def test_external_task_flows_through_orchestrator(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        external = _make_issue(
            id="ext-1",
            title="Review quarterly metrics",
            description="Analyze Q1 metrics and prepare summary.",
        )
        mock_client.list_issues.return_value = [external]
        mock_client.update_issue.return_value = _make_done("ext-1")
        mock_client.create_issue.return_value = _make_follow_up("ext-fu")

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        summary = await runner.run_once()

        # Orchestrator received the external task
        assert stub_orchestrator.calls[0]["task_id"] == "ext-1"
        assert "Analyze Q1 metrics" in stub_orchestrator.calls[0]["description"]

        # Its output flowed to Paperclip
        assert "[Orchestrator]" in summary["result"]
        assert "Review quarterly metrics" in summary["result"]

    async def test_skips_tasks_for_other_agents(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        other = _make_issue(id="other-1", assignee_id="agent-codex")
        mine = _make_issue(id="mine-1", title="My task")
        mock_client.list_issues.return_value = [other, mine]
        mock_client.update_issue.return_value = _make_done("mine-1")
        mock_client.create_issue.return_value = _make_follow_up()

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        summary = await runner.run_once()

        assert summary["original_issue_id"] == "mine-1"
        mock_client.checkout_issue.assert_awaited_once_with("mine-1")


# ═══════════════════════════════════════════════════════════════════════════════
# RECURSIVE CHAIN: follow-up → grabbed → orchestrator → follow-up → ...
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecursiveChain:
    """Multi-cycle chains where each follow-up becomes the next task."""

    async def test_two_cycle_chain(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        task_a = _make_issue(id="A", title="Initial musing")
        fu_b = PaperclipIssue(
            id="B", title="Follow-up: Initial musing",
            description="Continue", status="open",
            assignee_id=TIMMY_AGENT_ID, priority="normal",
        )
        fu_c = PaperclipIssue(
            id="C", title="Follow-up: Follow-up",
            status="open", assignee_id=TIMMY_AGENT_ID,
        )

        # Cycle 1
        mock_client.list_issues.return_value = [task_a]
        mock_client.update_issue.return_value = _make_done("A")
        mock_client.create_issue.return_value = fu_b

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        s1 = await runner.run_once()
        assert s1["original_issue_id"] == "A"
        assert s1["follow_up_issue_id"] == "B"

        # Cycle 2: follow-up B is now the task
        mock_client.list_issues.return_value = [fu_b]
        mock_client.update_issue.return_value = _make_done("B")
        mock_client.create_issue.return_value = fu_c

        s2 = await runner.run_once()
        assert s2["original_issue_id"] == "B"
        assert s2["follow_up_issue_id"] == "C"

        # Orchestrator was called twice — once per cycle
        assert len(stub_orchestrator.calls) == 2
        assert stub_orchestrator.calls[0]["task_id"] == "A"
        assert stub_orchestrator.calls[1]["task_id"] == "B"

    async def test_three_cycle_chain_all_through_orchestrator(
        self, mock_client, bridge, stub_orchestrator, settings_patch,
    ):
        """Three cycles — every task goes through the orchestrator pipe."""
        tasks = [_make_issue(id=f"c-{i}", title=f"Chain {i}") for i in range(3)]
        follow_ups = [
            PaperclipIssue(
                id=f"c-{i + 1}", title=f"Follow-up: Chain {i}",
                status="open", assignee_id=TIMMY_AGENT_ID,
            )
            for i in range(3)
        ]

        runner = TaskRunner(bridge=bridge, orchestrator=stub_orchestrator)
        ids = []

        for i in range(3):
            mock_client.list_issues.return_value = [tasks[i]]
            mock_client.update_issue.return_value = _make_done(tasks[i].id)
            mock_client.create_issue.return_value = follow_ups[i]

            s = await runner.run_once()
            ids.append(s["original_issue_id"])

        assert ids == ["c-0", "c-1", "c-2"]
        assert len(stub_orchestrator.calls) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# LIFECYCLE: start/stop
# ═══════════════════════════════════════════════════════════════════════════════


class TestLifecycle:

    async def test_stop_halts_loop(self, mock_client, bridge, settings_patch):
        runner = TaskRunner(bridge=bridge)
        runner._running = True
        runner.stop()
        assert runner._running is False

    async def test_start_disabled_when_interval_zero(
        self, mock_client, bridge, settings_patch,
    ):
        settings_patch.paperclip_poll_interval = 0
        runner = TaskRunner(bridge=bridge)
        await runner.start()
        mock_client.list_issues.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# LIVE LLM (manual e2e): runs only when Ollama is available
# ═══════════════════════════════════════════════════════════════════════════════


def _ollama_reachable() -> tuple[bool, list[str]]:
    """Return (reachable, model_names)."""
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
        resp.raise_for_status()
        names = [m["name"] for m in resp.json().get("models", [])]
        return True, names
    except Exception:
        return False, []


def _pick_tiny_model(available: list[str]) -> str | None:
    """Pick the smallest model available for e2e tests."""
    candidates = ["tinyllama", "phi", "qwen2:0.5b", "llama3.2:1b", "gemma:2b"]
    for candidate in candidates:
        for name in available:
            if candidate in name:
                return name
    return None


class LiveOllamaOrchestrator:
    """Thin orchestrator that calls Ollama directly — no Agno dependency."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.calls: list[dict] = []

    async def execute_task(
        self, task_id: str, description: str, context: dict
    ) -> str:
        import httpx as hx

        self.calls.append({"task_id": task_id, "description": description})

        async with hx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": (
                        f"You are Timmy, a task automation agent. "
                        f"Task: {description}\n"
                        f"Respond in 1-2 sentences about what you did."
                    ),
                    "stream": False,
                    "options": {"num_predict": 64},
                },
            )
            resp.raise_for_status()
            return resp.json()["response"]


@pytest.mark.ollama
class TestLiveOllamaGreenPath:
    """Green-path with a real tiny LLM via Ollama.

    Run with: ``tox -e ollama`` or ``pytest -m ollama``
    Requires: Ollama running with a small model.
    """

    async def test_live_full_cycle(self, mock_client, bridge, settings_patch):
        """Wire a real tiny LLM through the full pipe and verify output."""
        reachable, models = _ollama_reachable()
        if not reachable:
            pytest.skip("Ollama not reachable at localhost:11434")

        chosen = _pick_tiny_model(models)
        if not chosen:
            pytest.skip(f"No tiny model found (have: {models[:5]})")

        issue = _make_issue(
            id="live-1",
            title="Reflect on task automation",
            description="Muse about how you process tasks and suggest improvements.",
        )
        mock_client.list_issues.return_value = [issue]
        mock_client.update_issue.return_value = _make_done("live-1")
        mock_client.create_issue.return_value = _make_follow_up("live-fu")

        live_orch = LiveOllamaOrchestrator(chosen)
        runner = TaskRunner(bridge=bridge, orchestrator=live_orch)
        summary = await runner.run_once()

        # The LLM produced *something* non-empty
        assert summary is not None
        assert len(summary["result"]) > 0
        assert summary["completed"] is True
        assert summary["follow_up_issue_id"] == "live-fu"

        # Orchestrator was actually called
        assert len(live_orch.calls) == 1
        assert live_orch.calls[0]["task_id"] == "live-1"

        # LLM output flowed into the Paperclip comment
        comment = mock_client.add_comment.call_args[0][1]
        assert "[Timmy]" in comment
        assert len(comment) > len("[Timmy] Task completed.\n\n")

        # LLM output flowed into the follow-up description
        fu_req = mock_client.create_issue.call_args[0][0]
        assert len(fu_req.description) > 0
        assert fu_req.assignee_id == TIMMY_AGENT_ID

    async def test_live_recursive_chain(self, mock_client, bridge, settings_patch):
        """Two-cycle chain with a real LLM — each cycle produces real output."""
        reachable, models = _ollama_reachable()
        if not reachable:
            pytest.skip("Ollama not reachable")

        chosen = _pick_tiny_model(models)
        if not chosen:
            pytest.skip("No tiny model found")

        task_a = _make_issue(id="live-A", title="Initial reflection")
        fu_b = PaperclipIssue(
            id="live-B", title="Follow-up: Initial reflection",
            description="Continue reflecting", status="open",
            assignee_id=TIMMY_AGENT_ID, priority="normal",
        )
        fu_c = PaperclipIssue(
            id="live-C", title="Follow-up: Follow-up",
            status="open", assignee_id=TIMMY_AGENT_ID,
        )

        live_orch = LiveOllamaOrchestrator(chosen)
        runner = TaskRunner(bridge=bridge, orchestrator=live_orch)

        # Cycle 1
        mock_client.list_issues.return_value = [task_a]
        mock_client.update_issue.return_value = _make_done("live-A")
        mock_client.create_issue.return_value = fu_b

        s1 = await runner.run_once()
        assert s1 is not None
        assert len(s1["result"]) > 0

        # Cycle 2
        mock_client.list_issues.return_value = [fu_b]
        mock_client.update_issue.return_value = _make_done("live-B")
        mock_client.create_issue.return_value = fu_c

        s2 = await runner.run_once()
        assert s2 is not None
        assert len(s2["result"]) > 0

        # Both cycles went through the LLM
        assert len(live_orch.calls) == 2
