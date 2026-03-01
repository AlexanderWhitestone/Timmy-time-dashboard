import subprocess
from typing import Optional

import typer

from timmy.agent import create_timmy
from timmy.prompts import TIMMY_STATUS_PROMPT

app = typer.Typer(help="Timmy — sovereign AI agent")

# Shared option definitions (reused across commands for consistency).
_BACKEND_OPTION = typer.Option(
    None,
    "--backend",
    "-b",
    help="Inference backend: 'ollama' (default) | 'airllm' | 'auto'",
)
_MODEL_SIZE_OPTION = typer.Option(
    None,
    "--model-size",
    "-s",
    help="AirLLM model size when --backend airllm: '8b' | '70b' | '405b'",
)


@app.command()
def think(
    topic: str = typer.Argument(..., help="Topic to reason about"),
    backend: Optional[str] = _BACKEND_OPTION,
    model_size: Optional[str] = _MODEL_SIZE_OPTION,
):
    """Ask Timmy to think carefully about a topic."""
    timmy = create_timmy(backend=backend, model_size=model_size)
    timmy.print_response(f"Think carefully about: {topic}", stream=True)


@app.command()
def chat(
    message: str = typer.Argument(..., help="Message to send"),
    backend: Optional[str] = _BACKEND_OPTION,
    model_size: Optional[str] = _MODEL_SIZE_OPTION,
):
    """Send a message to Timmy."""
    timmy = create_timmy(backend=backend, model_size=model_size)
    timmy.print_response(message, stream=True)


@app.command()
def status(
    backend: Optional[str] = _BACKEND_OPTION,
    model_size: Optional[str] = _MODEL_SIZE_OPTION,
):
    """Print Timmy's operational status."""
    timmy = create_timmy(backend=backend, model_size=model_size)
    timmy.print_response(TIMMY_STATUS_PROMPT, stream=False)


@app.command()
def interview(
    backend: Optional[str] = _BACKEND_OPTION,
    model_size: Optional[str] = _MODEL_SIZE_OPTION,
):
    """Initialize Timmy and run a structured interview.

    Asks Timmy a series of questions about his identity, capabilities,
    values, and operation to verify he is working correctly.
    """
    from timmy.interview import InterviewEntry, format_transcript, run_interview
    from timmy.session import chat

    typer.echo("Initializing Timmy for interview...\n")

    # Force agent creation by calling chat once with a warm-up prompt
    try:
        chat("Hello, Timmy. We're about to start your interview.", session_id="interview")
    except Exception as exc:
        typer.echo(f"Warning: Initialization issue — {exc}", err=True)

    def _on_answer(entry: InterviewEntry) -> None:
        typer.echo(f"[{entry.category}]")
        typer.echo(f"  Q: {entry.question}")
        typer.echo(f"  A: {entry.answer}")
        typer.echo()

    typer.echo("Starting interview...\n")
    transcript = run_interview(
        chat_fn=lambda msg: chat(msg, session_id="interview"),
        on_answer=_on_answer,
    )

    # Print full transcript at the end
    typer.echo("\n" + format_transcript(transcript))


@app.command()
def up(
    dev: bool = typer.Option(False, "--dev", help="Enable hot-reload for development"),
    build: bool = typer.Option(True, "--build/--no-build", help="Rebuild images before starting"),
):
    """Start Timmy Time in Docker (dashboard + agents)."""
    cmd = ["docker", "compose"]
    if dev:
        cmd += ["-f", "docker-compose.yml", "-f", "docker-compose.dev.yml"]
    cmd += ["up", "-d"]
    if build:
        cmd.append("--build")

    mode = "dev mode (hot-reload active)" if dev else "production mode"
    typer.echo(f"Starting Timmy Time in {mode}...")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        typer.echo(f"\n  Timmy Time running at http://localhost:8000  ({mode})\n")
    else:
        typer.echo("Failed to start. Is Docker running?", err=True)
        raise typer.Exit(1)


@app.command()
def down():
    """Stop all Timmy Time Docker containers."""
    subprocess.run(["docker", "compose", "down"], check=True)


@app.command(name="ingest-report")
def ingest_report(
    file: Optional[str] = typer.Argument(
        None, help="Path to JSON report file (reads stdin if omitted)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate report and show what would be created",
    ),
):
    """Ingest a structured test report and create bug_report tasks.

    Reads a JSON report with an array of bugs and creates one task per bug
    in the internal task queue.  The task processor will then attempt to
    create GitHub Issues for each.

    Examples:
        timmy ingest-report report.json
        timmy ingest-report --dry-run report.json
        cat report.json | timmy ingest-report
    """
    import json
    import sys

    # Read input
    if file:
        try:
            with open(file) as f:
                raw = f.read()
        except FileNotFoundError:
            typer.echo(f"File not found: {file}", err=True)
            raise typer.Exit(1)
    else:
        if sys.stdin.isatty():
            typer.echo("Reading from stdin (paste JSON, then Ctrl+D)...")
        raw = sys.stdin.read()

    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON: {exc}", err=True)
        raise typer.Exit(1)

    reporter = data.get("reporter", "unknown")
    bugs = data.get("bugs", [])

    if not bugs:
        typer.echo("No bugs in report.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Report: {len(bugs)} bug(s) from {reporter}")

    if dry_run:
        for bug in bugs:
            typer.echo(f"  [{bug.get('severity', '?')}] {bug.get('title', '(no title)')}")
        typer.echo("(dry run — no tasks created)")
        return

    # Import and create tasks
    from swarm.task_queue.models import create_task

    severity_map = {"P0": "urgent", "P1": "high", "P2": "normal"}
    created = 0
    for bug in bugs:
        title = bug.get("title", "")
        severity = bug.get("severity", "P2")
        description = bug.get("description", "")

        if not title or not description:
            typer.echo(f"  SKIP (missing title or description)")
            continue

        # Format description with extra fields
        parts = [f"**Reporter:** {reporter}", f"**Severity:** {severity}", "", description]
        if bug.get("evidence"):
            parts += ["", "## Evidence", bug["evidence"]]
        if bug.get("root_cause"):
            parts += ["", "## Root Cause", bug["root_cause"]]
        if bug.get("fix_options"):
            parts += ["", "## Fix Options"]
            for i, fix in enumerate(bug["fix_options"], 1):
                parts.append(f"{i}. {fix}")

        task = create_task(
            title=f"[{severity}] {title}",
            description="\n".join(parts),
            task_type="bug_report",
            assigned_to="timmy",
            created_by=reporter,
            priority=severity_map.get(severity, "normal"),
            requires_approval=False,
            auto_approve=True,
        )
        typer.echo(f"  OK [{severity}] {title} → {task.id}")
        created += 1

    typer.echo(f"\n{created} task(s) created.")


def main():
    app()
