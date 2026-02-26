"""API endpoints for Cascade Router monitoring and control."""

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .cascade import CascadeRouter, get_router

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/router", tags=["router"])


class CompletionRequest(BaseModel):
    """Request body for completions."""
    messages: list[dict[str, str]]
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None


class CompletionResponse(BaseModel):
    """Response from completion endpoint."""
    content: str
    provider: str
    model: str
    latency_ms: float


class ProviderControl(BaseModel):
    """Control a provider's status."""
    action: str  # "enable", "disable", "reset_circuit"


async def get_cascade_router() -> CascadeRouter:
    """Dependency to get the cascade router."""
    return get_router()


@router.post("/complete", response_model=CompletionResponse)
async def complete(
    request: CompletionRequest,
    cascade: Annotated[CascadeRouter, Depends(get_cascade_router)],
) -> dict[str, Any]:
    """Complete a conversation with automatic failover.
    
    Routes through providers in priority order until one succeeds.
    """
    try:
        result = await cascade.complete(
            messages=request.messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/status")
async def get_status(
    cascade: Annotated[CascadeRouter, Depends(get_cascade_router)],
) -> dict[str, Any]:
    """Get router status and provider health."""
    return cascade.get_status()


@router.get("/metrics")
async def get_metrics(
    cascade: Annotated[CascadeRouter, Depends(get_cascade_router)],
) -> dict[str, Any]:
    """Get detailed metrics for all providers."""
    return cascade.get_metrics()


@router.get("/providers")
async def list_providers(
    cascade: Annotated[CascadeRouter, Depends(get_cascade_router)],
) -> list[dict[str, Any]]:
    """List all configured providers."""
    return [
        {
            "name": p.name,
            "type": p.type,
            "enabled": p.enabled,
            "priority": p.priority,
            "status": p.status.value,
            "circuit_state": p.circuit_state.value,
            "default_model": p.get_default_model(),
            "models": [m["name"] for m in p.models],
        }
        for p in cascade.providers
    ]


@router.post("/providers/{provider_name}/control")
async def control_provider(
    provider_name: str,
    control: ProviderControl,
    cascade: Annotated[CascadeRouter, Depends(get_cascade_router)],
) -> dict[str, str]:
    """Control a provider (enable/disable/reset)."""
    provider = None
    for p in cascade.providers:
        if p.name == provider_name:
            provider = p
            break
    
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {provider_name} not found")
    
    if control.action == "enable":
        provider.enabled = True
        provider.status = provider.status.__class__.HEALTHY
        return {"message": f"Provider {provider_name} enabled"}
    
    elif control.action == "disable":
        provider.enabled = False
        from .cascade import ProviderStatus
        provider.status = ProviderStatus.DISABLED
        return {"message": f"Provider {provider_name} disabled"}
    
    elif control.action == "reset_circuit":
        from .cascade import CircuitState, ProviderStatus
        provider.circuit_state = CircuitState.CLOSED
        provider.circuit_opened_at = None
        provider.half_open_calls = 0
        provider.metrics.consecutive_failures = 0
        provider.status = ProviderStatus.HEALTHY
        return {"message": f"Circuit breaker reset for {provider_name}"}
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {control.action}")


@router.post("/health-check")
async def run_health_check(
    cascade: Annotated[CascadeRouter, Depends(get_cascade_router)],
) -> dict[str, Any]:
    """Run health checks on all providers."""
    results = []
    
    for provider in cascade.providers:
        # Quick ping to check availability
        is_healthy = cascade._check_provider_available(provider)
        
        from .cascade import ProviderStatus
        if is_healthy:
            if provider.status == ProviderStatus.UNHEALTHY:
                # Reset circuit if it was open but now healthy
                provider.circuit_state = provider.circuit_state.__class__.CLOSED
                provider.circuit_opened_at = None
            provider.status = ProviderStatus.HEALTHY if provider.metrics.error_rate < 0.1 else ProviderStatus.DEGRADED
        else:
            provider.status = ProviderStatus.UNHEALTHY
        
        results.append({
            "name": provider.name,
            "type": provider.type,
            "healthy": is_healthy,
            "status": provider.status.value,
        })
    
    return {
        "checked_at": asyncio.get_event_loop().time(),
        "providers": results,
        "healthy_count": sum(1 for r in results if r["healthy"]),
    }


@router.get("/config")
async def get_config(
    cascade: Annotated[CascadeRouter, Depends(get_cascade_router)],
) -> dict[str, Any]:
    """Get router configuration (without secrets)."""
    cfg = cascade.config
    
    return {
        "timeout_seconds": cfg.timeout_seconds,
        "max_retries_per_provider": cfg.max_retries_per_provider,
        "retry_delay_seconds": cfg.retry_delay_seconds,
        "circuit_breaker": {
            "failure_threshold": cfg.circuit_breaker_failure_threshold,
            "recovery_timeout": cfg.circuit_breaker_recovery_timeout,
            "half_open_max_calls": cfg.circuit_breaker_half_open_max_calls,
        },
        "providers": [
            {
                "name": p.name,
                "type": p.type,
                "priority": p.priority,
                "enabled": p.enabled,
            }
            for p in cascade.providers
        ],
    }
