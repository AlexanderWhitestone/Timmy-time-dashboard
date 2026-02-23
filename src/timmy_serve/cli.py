"""Serve-mode CLI — run Timmy as a paid service agent.

This CLI starts Timmy in "serve" mode where it accepts requests
gated by L402 Lightning payments.  This is the economic layer that
makes Timmy a sovereign agent — it earns sats for its work.

Usage:
    timmy-serve start [--port 8402]
    timmy-serve invoice --amount 100 --memo "API access"
    timmy-serve status
"""

import typer

app = typer.Typer(help="Timmy Serve — sovereign AI agent with Lightning payments")


@app.command()
def start(
    port: int = typer.Option(8402, "--port", "-p", help="Port for the serve API"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    price: int = typer.Option(100, "--price", help="Price per request in sats"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print config and exit (for testing)"),
):
    """Start Timmy in serve mode with L402 payment gating."""
    typer.echo(f"Starting Timmy Serve on {host}:{port}")
    typer.echo(f"L402 payment proxy active — {price} sats per request")
    typer.echo("Press Ctrl-C to stop")
    
    typer.echo(f"\nEndpoints:")
    typer.echo(f"  POST /serve/chat    — L402-gated chat (pay per request)")
    typer.echo(f"  GET  /serve/invoice — Request a Lightning invoice")
    typer.echo(f"  GET  /serve/status  — Service status")
    typer.echo(f"  GET  /health        — Health check")
    
    if dry_run:
        typer.echo("\n(Dry run mode - not starting server)")
        return
    
    import uvicorn
    from timmy_serve.app import create_timmy_serve_app
    
    # Create and run the FastAPI app
    serve_app = create_timmy_serve_app(price_sats=price)
    uvicorn.run(serve_app, host=host, port=port)


@app.command()
def invoice(
    amount: int = typer.Option(100, "--amount", "-a", help="Invoice amount in sats"),
    memo: str = typer.Option("API access", "--memo", "-m", help="Invoice memo"),
):
    """Create a Lightning invoice."""
    from timmy_serve.payment_handler import payment_handler

    inv = payment_handler.create_invoice(amount, memo)
    typer.echo(f"Invoice created:")
    typer.echo(f"  Amount:       {inv.amount_sats} sats")
    typer.echo(f"  Memo:         {inv.memo}")
    typer.echo(f"  Payment hash: {inv.payment_hash}")
    typer.echo(f"  Pay request:  {inv.payment_request}")


@app.command()
def status():
    """Show serve-mode status."""
    from timmy_serve.payment_handler import payment_handler

    invoices = payment_handler.list_invoices()
    settled = [i for i in invoices if i.settled]
    typer.echo("Timmy Serve — Status")
    typer.echo(f"  Total invoices: {len(invoices)}")
    typer.echo(f"  Settled:        {len(settled)}")
    total_sats = sum(i.amount_sats for i in settled)
    typer.echo(f"  Total earned:   {total_sats} sats")


def main():
    app()
