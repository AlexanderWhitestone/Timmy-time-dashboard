"""Health and sovereignty status endpoints.

Provides system health checks and sovereignty audit information
for the Mission Control dashboard.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class DependencyStatus(BaseModel):
    """Status of a single dependency."""
    name: str
    status: str  # "healthy", "degraded", "unavailable"
    sovereignty_score: int  # 0-10
    details: dict[str, Any]


class SovereigntyReport(BaseModel):
    """Full sovereignty audit report."""
    overall_score: float
    dependencies: list[DependencyStatus]
    timestamp: str
    recommendations: list[str]


class HealthStatus(BaseModel):
    """System health status."""
    status: str
    timestamp: str
    version: str
    uptime_seconds: float


# Simple uptime tracking
_START_TIME = datetime.now(timezone.utc)


def _check_ollama_sync() -> DependencyStatus:
    """Synchronous Ollama check — run via asyncio.to_thread()."""
    try:
        import urllib.request
        url = settings.ollama_url.replace("localhost", "127.0.0.1")
        req = urllib.request.Request(
            f"{url}/api/tags",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                return DependencyStatus(
                    name="Ollama AI",
                    status="healthy",
                    sovereignty_score=10,
                    details={"url": settings.ollama_url, "model": settings.ollama_model},
                )
    except Exception:
        pass

    return DependencyStatus(
        name="Ollama AI",
        status="unavailable",
        sovereignty_score=10,
        details={"url": settings.ollama_url, "error": "Cannot connect to Ollama"},
    )


async def _check_ollama() -> DependencyStatus:
    """Check Ollama AI backend status without blocking the event loop."""
    try:
        return await asyncio.to_thread(_check_ollama_sync)
    except Exception:
        return DependencyStatus(
            name="Ollama AI",
            status="unavailable",
            sovereignty_score=10,
            details={"url": settings.ollama_url, "error": "Cannot connect to Ollama"},
        )


async def check_ollama() -> bool:
    """Legacy bool check — used by health_check endpoint."""
    dep = await _check_ollama()
    return dep.status == "healthy"


def _check_lightning() -> DependencyStatus:
    """Check Lightning payment backend status."""
    return DependencyStatus(
        name="Lightning Payments",
        status="unavailable",
        sovereignty_score=8,
        details={"note": "Lightning module removed — will be re-added in v2"},
    )


def _check_sqlite() -> DependencyStatus:
    """Check SQLite database status."""
    try:
        import sqlite3
        from pathlib import Path

        db_path = Path(settings.repo_root) / "data" / "timmy.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("SELECT 1")
        conn.close()

        return DependencyStatus(
            name="SQLite Database",
            status="healthy",
            sovereignty_score=10,
            details={"path": str(db_path)},
        )
    except Exception as exc:
        return DependencyStatus(
            name="SQLite Database",
            status="unavailable",
            sovereignty_score=10,
            details={"error": str(exc)},
        )


def _calculate_overall_score(deps: list[DependencyStatus]) -> float:
    """Calculate overall sovereignty score."""
    if not deps:
        return 0.0
    return round(sum(d.sovereignty_score for d in deps) / len(deps), 1)


def _generate_recommendations(deps: list[DependencyStatus]) -> list[str]:
    """Generate recommendations based on dependency status."""
    recommendations = []
    
    for dep in deps:
        if dep.status == "unavailable":
            recommendations.append(f"{dep.name} is unavailable - check configuration")
        elif dep.status == "degraded":
            if dep.name == "Lightning Payments" and dep.details.get("backend") == "mock":
                recommendations.append(
                    "Switch to real Lightning: set LIGHTNING_BACKEND=lnd and configure LND"
                )
    
    if not recommendations:
        recommendations.append("System operating optimally - all dependencies healthy")
    
    return recommendations


@router.get("/health")
async def health_check():
    """Basic health check endpoint.
    
    Returns legacy format for backward compatibility with existing tests,
    plus extended information for the Mission Control dashboard.
    """
    uptime = (datetime.now(timezone.utc) - _START_TIME).total_seconds()
    
    # Legacy format for test compatibility
    ollama_ok = await check_ollama()
    
    agent_status = "idle" if ollama_ok else "offline"

    return {
        "status": "ok" if ollama_ok else "degraded",
        "services": {
            "ollama": "up" if ollama_ok else "down",
        },
        "agents": {
            "agent": {"status": agent_status},
        },
        # Extended fields for Mission Control
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "uptime_seconds": uptime,
        "llm_backend": settings.timmy_model_backend,
        "llm_model": settings.ollama_model,
    }


@router.get("/health/status", response_class=HTMLResponse)
async def health_status_panel(request: Request):
    """Simple HTML health status panel."""
    ollama_ok = await check_ollama()
    
    status_text = "UP" if ollama_ok else "DOWN"
    status_color = "#10b981" if ollama_ok else "#ef4444"
    import html
    model = html.escape(settings.ollama_model)  # Include model for test compatibility
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Health Status</title></head>
    <body style="font-family: monospace; padding: 20px;">
        <h1>System Health</h1>
        <p>Ollama: <span style="color: {status_color}; font-weight: bold;">{status_text}</span></p>
        <p>Model: {model}</p>
        <p>Timestamp: {datetime.now(timezone.utc).isoformat()}</p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/health/sovereignty", response_model=SovereigntyReport)
async def sovereignty_check():
    """Comprehensive sovereignty audit report.
    
    Returns the status of all external dependencies with sovereignty scores.
    Use this to verify the system is operating in a sovereign manner.
    """
    dependencies = [
        await _check_ollama(),
        _check_lightning(),
        _check_sqlite(),
    ]
    
    overall = _calculate_overall_score(dependencies)
    recommendations = _generate_recommendations(dependencies)
    
    return SovereigntyReport(
        overall_score=overall,
        dependencies=dependencies,
        timestamp=datetime.now(timezone.utc).isoformat(),
        recommendations=recommendations,
    )


@router.get("/health/components")
async def component_status():
    """Get status of all system components."""
    return {
        "config": {
            "debug": settings.debug,
            "model_backend": settings.timmy_model_backend,
            "ollama_model": settings.ollama_model,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
