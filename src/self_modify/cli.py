"""CLI for self-modification — run from the terminal.

Usage:
    self-modify run "Add a docstring to src/timmy/prompts.py" --file src/timmy/prompts.py
    self-modify run "Fix the bug in config" --dry-run
    self-modify run "Add logging" --backend anthropic --autonomous
    self-modify status
"""

import logging
import os
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()
app = typer.Typer(help="Timmy self-modify — edit code, run tests, commit")


@app.command()
def run(
    instruction: str = typer.Argument(..., help="What to change (natural language)"),
    file: Optional[list[str]] = typer.Option(None, "--file", "-f", help="Target file(s) to modify"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Generate edits but don't write"),
    retries: int = typer.Option(2, "--retries", "-r", help="Max retry attempts on test failure"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="LLM backend: ollama, anthropic, auto"),
    autonomous: bool = typer.Option(False, "--autonomous", "-a", help="Enable autonomous self-correction"),
    max_cycles: int = typer.Option(3, "--max-cycles", help="Max autonomous correction cycles"),
    branch: bool = typer.Option(False, "--branch", help="Create a git branch (off by default to avoid container restarts)"),
    speak: bool = typer.Option(False, "--speak", "-s", help="Speak the result via TTS"),
):
    """Run the self-modification loop."""
    # Force enable for CLI usage
    os.environ["SELF_MODIFY_ENABLED"] = "true"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s -- %(message)s",
        datefmt="%H:%M:%S",
    )

    # Skip branch creation unless explicitly requested
    if not branch:
        os.environ["SELF_MODIFY_SKIP_BRANCH"] = "1"

    from self_modify.loop import SelfModifyLoop, ModifyRequest

    target_files = list(file) if file else []
    effective_backend = backend or os.environ.get("SELF_MODIFY_BACKEND", "auto")

    console.print(Panel(
        f"[bold]Instruction:[/bold] {instruction}\n"
        f"[bold]Files:[/bold] {', '.join(target_files) or '(auto-detect)'}\n"
        f"[bold]Backend:[/bold] {effective_backend}\n"
        f"[bold]Autonomous:[/bold] {autonomous}\n"
        f"[bold]Dry run:[/bold] {dry_run}\n"
        f"[bold]Max retries:[/bold] {retries}",
        title="Self-Modify",
        border_style="cyan",
    ))

    loop = SelfModifyLoop(
        max_retries=retries,
        backend=effective_backend,
        autonomous=autonomous,
        max_autonomous_cycles=max_cycles,
    )
    request = ModifyRequest(
        instruction=instruction,
        target_files=target_files,
        dry_run=dry_run,
    )

    with console.status("[bold cyan]Running self-modification loop..."):
        result = loop.run(request)

    if result.report_path:
        console.print(f"\n[dim]Report saved: {result.report_path}[/dim]\n")

    if result.success:
        console.print(Panel(
            f"[green bold]SUCCESS[/green bold]\n\n"
            f"Files changed: {', '.join(result.files_changed)}\n"
            f"Tests passed: {result.test_passed}\n"
            f"Commit: {result.commit_sha or 'none (dry run)'}\n"
            f"Branch: {result.branch_name or 'current'}\n"
            f"Attempts: {result.attempts}\n"
            f"Autonomous cycles: {result.autonomous_cycles}",
            title="Result",
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[red bold]FAILED[/red bold]\n\n"
            f"Error: {result.error}\n"
            f"Attempts: {result.attempts}\n"
            f"Autonomous cycles: {result.autonomous_cycles}",
            title="Result",
            border_style="red",
        ))
        raise typer.Exit(1)

    if speak and result.success:
        try:
            from timmy_serve.voice_tts import voice_tts
            if voice_tts.available:
                voice_tts.speak_sync(
                    f"Code modification complete. "
                    f"{len(result.files_changed)} files changed. Tests passing."
                )
        except Exception:
            pass


@app.command()
def status():
    """Show whether self-modification is enabled."""
    from config import settings
    enabled = settings.self_modify_enabled
    color = "green" if enabled else "red"
    console.print(f"Self-modification: [{color}]{'ENABLED' if enabled else 'DISABLED'}[/{color}]")
    console.print(f"Max retries: {settings.self_modify_max_retries}")
    console.print(f"Backend: {settings.self_modify_backend}")
    console.print(f"Allowed dirs: {settings.self_modify_allowed_dirs}")


def main():
    app()


if __name__ == "__main__":
    main()
