"""Serve-mode CLI — run Timmy as an API service.

Usage:
    timmy-serve start [--port 8402]
    timmy-serve status
"""

import typer

app = typer.Typer(help="Timmy Serve — sovereign AI agent API")


@app.command()
def start(
    port: int = typer.Option(8402, "--port", "-p", help="Port for the serve API"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    price: int = typer.Option(100, "--price", help="Price per request in sats"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print config and exit (for testing)"),
):
    """Start Timmy in serve mode."""
    typer.echo(f"Starting Timmy Serve on {host}:{port}")
    typer.echo(f"L402 payment proxy active — {price} sats per request")
    typer.echo("Press Ctrl-C to stop")

    typer.echo(f"\nEndpoints:")
    typer.echo(f"  POST /serve/chat    — Chat with Timmy")
    typer.echo(f"  GET  /serve/invoice — Request an invoice")
    typer.echo(f"  GET  /serve/status  — Service status")
    typer.echo(f"  GET  /health        — Health check")

    if dry_run:
        typer.echo("\n(Dry run mode - not starting server)")
        return

    import uvicorn
    from timmy_serve.app import create_timmy_serve_app

    serve_app = create_timmy_serve_app()
    uvicorn.run(serve_app, host=host, port=port)


@app.command()
def status():
    """Show serve-mode status."""
    typer.echo("Timmy Serve — Status")
    typer.echo("  Service: active")


def main():
    app()
