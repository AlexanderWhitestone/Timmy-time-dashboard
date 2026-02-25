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


def main():
    app()
