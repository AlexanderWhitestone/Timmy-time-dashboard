"""Timmy Serve — FastAPI app with L402 payment gating.

Provides a paid API for Timmy's services, gated by Lightning payments
via the L402 protocol.

Endpoints:
  POST /serve/chat    — L402-gated chat (pay per request)
  GET  /serve/invoice — Request a Lightning invoice
  GET  /serve/status  — Service status
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
from timmy.agent import create_timmy
from timmy_serve.l402_proxy import create_l402_challenge, verify_l402_token
from timmy_serve.payment_handler import payment_handler

logger = logging.getLogger(__name__)

# Default pricing (sats per request)
DEFAULT_PRICE_SATS = 100


class ChatRequest(BaseModel):
    message: str
    stream: bool = False


class ChatResponse(BaseModel):
    response: str
    payment_hash: Optional[str] = None


class InvoiceRequest(BaseModel):
    amount_sats: int = DEFAULT_PRICE_SATS
    memo: str = "Timmy API access"


class InvoiceResponse(BaseModel):
    payment_request: str
    payment_hash: str
    amount_sats: int


class StatusResponse(BaseModel):
    status: str
    backend: str
    price_sats: int
    total_invoices: int
    total_earned_sats: int


def create_timmy_serve_app(price_sats: int = DEFAULT_PRICE_SATS) -> FastAPI:
    """Create the Timmy Serve FastAPI application with L402 middleware.
    
    Args:
        price_sats: Default price per API request in satoshis
    
    Returns:
        Configured FastAPI application
    """
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Timmy Serve starting — price: %d sats/request", price_sats)
        yield
        logger.info("Timmy Serve shutting down")
    
    app = FastAPI(
        title="Timmy Serve — Sovereign AI API",
        description="Lightning-gated API access to Timmy",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )
    
    # Store price in app state for middleware access
    app.state.price_sats = price_sats
    
    @app.middleware("http")
    async def l402_middleware(request: Request, call_next):
        """Middleware to enforce L402 payment for protected endpoints."""
        
        # Only protect /serve/chat endpoint
        if request.url.path != "/serve/chat":
            return await call_next(request)
        
        # Skip for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Check for L402 token in Authorization header
        auth_header = request.headers.get("authorization", "")
        
        if auth_header.startswith("L402 "):
            token = auth_header[5:]  # Remove "L402 " prefix
            # Check for token:preimage format
            if ":" in token:
                macaroon, preimage = token.split(":", 1)
                if verify_l402_token(macaroon, preimage):
                    # Payment verified, proceed
                    return await call_next(request)
        
        # No valid payment, return 402 Payment Required
        challenge = create_l402_challenge(price_sats, "Timmy API request")
        
        return JSONResponse(
            status_code=402,
            content={
                "error": "Payment Required",
                "code": "L402",
                "macaroon": challenge["macaroon"],
                "invoice": challenge["invoice"],
                "payment_hash": challenge["payment_hash"],
                "amount_sats": price_sats,
            },
            headers={
                "WWW-Authenticate": f'L402 macaroon="{challenge["macaroon"]}", invoice="{challenge["invoice"]}"',
            },
        )
    
    @app.get("/serve/status", response_model=StatusResponse)
    async def serve_status():
        """Get service status and pricing information."""
        invoices = payment_handler.list_invoices(settled_only=True)
        total_earned = sum(i.amount_sats for i in invoices)
        
        return StatusResponse(
            status="active",
            backend=settings.timmy_model_backend,
            price_sats=price_sats,
            total_invoices=len(payment_handler.list_invoices()),
            total_earned_sats=total_earned,
        )
    
    @app.post("/serve/invoice", response_model=InvoiceResponse)
    async def serve_invoice(request: InvoiceRequest):
        """Create a Lightning invoice for API access."""
        invoice = payment_handler.create_invoice(
            amount_sats=request.amount_sats,
            memo=request.memo,
        )
        
        return InvoiceResponse(
            payment_request=invoice.payment_request,
            payment_hash=invoice.payment_hash,
            amount_sats=invoice.amount_sats,
        )
    
    @app.post("/serve/chat", response_model=ChatResponse)
    async def serve_chat(request: ChatRequest):
        """Process a chat request (L402-gated).
        
        Requires valid L402 token in Authorization header:
            Authorization: L402 <macaroon>:<preimage>
        """
        try:
            # Create Timmy agent and process request
            timmy = create_timmy()
            result = timmy.run(request.message, stream=False)
            response_text = result.content if hasattr(result, "content") else str(result)
            
            # Get payment hash from Authorization header for receipt
            auth_header = request.headers.get("authorization", "")
            payment_hash = None
            if auth_header.startswith("L402 ") and ":" in auth_header[5:]:
                macaroon = auth_header[5:].split(":", 1)[0]
                # Extract payment hash from macaroon (it's the identifier)
                try:
                    import base64
                    raw = base64.urlsafe_b64decode(macaroon.encode()).decode()
                    parts = raw.split(":")
                    if len(parts) == 4:
                        payment_hash = parts[2]
                except Exception:
                    pass
            
            return ChatResponse(
                response=response_text,
                payment_hash=payment_hash,
            )
        
        except Exception as exc:
            logger.error("Chat processing error: %s", exc)
            raise HTTPException(status_code=500, detail=f"Processing error: {exc}")
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "service": "timmy-serve"}
    
    return app


# Default app instance for uvicorn
timmy_serve_app = create_timmy_serve_app()
