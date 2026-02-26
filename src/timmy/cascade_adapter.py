"""Cascade Router adapter for Timmy agent.

Provides automatic failover between LLM providers with:
- Circuit breaker pattern for failing providers
- Metrics tracking per provider
- Priority-based routing (local first, then APIs)
"""

import logging
from dataclasses import dataclass
from typing import Optional

from router.cascade import CascadeRouter
from timmy.prompts import TIMMY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class TimmyResponse:
    """Response from Timmy via Cascade Router."""
    content: str
    provider_used: str
    latency_ms: float
    fallback_used: bool = False


class TimmyCascadeAdapter:
    """Adapter that routes Timmy requests through Cascade Router.
    
    Usage:
        adapter = TimmyCascadeAdapter()
        response = await adapter.chat("Hello")
        print(f"Response: {response.content}")
        print(f"Provider: {response.provider_used}")
    """
    
    def __init__(self, router: Optional[CascadeRouter] = None) -> None:
        """Initialize adapter with Cascade Router.
        
        Args:
            router: CascadeRouter instance. If None, creates default.
        """
        self.router = router or CascadeRouter()
        logger.info("TimmyCascadeAdapter initialized with %d providers", 
                   len(self.router.providers))
    
    async def chat(self, message: str, context: Optional[str] = None) -> TimmyResponse:
        """Send message through cascade router with automatic failover.
        
        Args:
            message: User message
            context: Optional conversation context
            
        Returns:
            TimmyResponse with content and metadata
        """
        # Build messages array
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": message})
        
        # Route through cascade
        import time
        start = time.time()
        
        try:
            result = await self.router.complete(
                messages=messages,
                system_prompt=TIMMY_SYSTEM_PROMPT,
            )
            
            latency = (time.time() - start) * 1000
            
            # Determine if fallback was used
            primary = self.router.providers[0] if self.router.providers else None
            fallback_used = primary and primary.status.value != "healthy"
            
            return TimmyResponse(
                content=result.content,
                provider_used=result.provider_name,
                latency_ms=latency,
                fallback_used=fallback_used,
            )
            
        except Exception as exc:
            logger.error("All providers failed: %s", exc)
            raise
    
    def get_provider_status(self) -> list[dict]:
        """Get status of all providers.
        
        Returns:
            List of provider status dicts
        """
        return [
            {
                "name": p.name,
                "type": p.type,
                "status": p.status.value,
                "circuit_state": p.circuit_state.value,
                "metrics": {
                    "total": p.metrics.total_requests,
                    "success": p.metrics.successful_requests,
                    "failed": p.metrics.failed_requests,
                    "avg_latency_ms": round(p.metrics.avg_latency_ms, 1),
                    "error_rate": round(p.metrics.error_rate, 3),
                },
                "priority": p.priority,
                "enabled": p.enabled,
            }
            for p in self.router.providers
        ]
    
    def get_preferred_provider(self) -> Optional[str]:
        """Get name of highest-priority healthy provider.
        
        Returns:
            Provider name or None if all unhealthy
        """
        for provider in self.router.providers:
            if provider.status.value == "healthy" and provider.enabled:
                return provider.name
        return None


# Global singleton for reuse
_cascade_adapter: Optional[TimmyCascadeAdapter] = None


def get_cascade_adapter() -> TimmyCascadeAdapter:
    """Get or create global cascade adapter singleton."""
    global _cascade_adapter
    if _cascade_adapter is None:
        _cascade_adapter = TimmyCascadeAdapter()
    return _cascade_adapter
