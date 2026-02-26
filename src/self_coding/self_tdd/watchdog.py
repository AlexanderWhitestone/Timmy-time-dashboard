"""Self-TDD Watchdog — polls pytest on a schedule and reports regressions.

Run in a terminal alongside your normal dev work:

    self-tdd watch
    self-tdd watch --interval 30

The watchdog runs silently while tests pass. When a regression appears it
prints the full short-traceback output so you can see exactly what broke.
No files are modified; no commits are made. Ctrl-C to stop.
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import typer

# Project root is three levels up from src/self_tdd/watchdog.py
PROJECT_ROOT = Path(__file__).parent.parent.parent

app = typer.Typer(help="Self-TDD watchdog — continuous test runner")


def _run_tests() -> tuple[bool, str]:
    """Run the test suite and return (passed, combined_output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=60,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


@app.command()
def watch(
    interval: int = typer.Option(60, "--interval", "-i", help="Seconds between test runs"),
) -> None:
    """Poll pytest continuously and print regressions as they appear."""
    typer.echo(f"Self-TDD watchdog started — polling every {interval}s. Ctrl-C to stop.")
    last_passed: bool | None = None

    try:
        while True:
            passed, output = _run_tests()
            stamp = datetime.now().strftime("%H:%M:%S")

            if passed:
                if last_passed is not True:
                    typer.secho(f"[{stamp}] All tests passing.", fg=typer.colors.GREEN)
            else:
                typer.secho(f"[{stamp}] Regression detected:", fg=typer.colors.RED)
                typer.echo(output)

            last_passed = passed
            time.sleep(interval)

    except KeyboardInterrupt:
        typer.echo("\nWatchdog stopped.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
