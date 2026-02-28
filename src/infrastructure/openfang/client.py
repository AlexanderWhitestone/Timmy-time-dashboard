"""OpenFang HTTP client — bridge between Timmy coordinator and OpenFang runtime.

Follows project conventions:
- Graceful degradation (log error, return fallback, never crash)
- Config via ``from config import settings``
- Singleton pattern for module-level import

The client wraps OpenFang's REST API and exposes its Hands
(Browser, Collector, Predictor, Lead, Twitter, Researcher, Clip)
as callable tool endpoints.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)

# Hand names that OpenFang ships out of the box
OPENFANG_HANDS = (
    "browser",
    "collector",
    "predictor",
    "lead",
    "twitter",
    "researcher",
    "clip",
)


@dataclass
class HandResult:
    """Result from an OpenFang Hand execution."""

    hand: str
    success: bool
    output: str = ""
    error: str = ""
    latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


class OpenFangClient:
    """HTTP client for the OpenFang sidecar.

    All methods degrade gracefully — if OpenFang is down the client
    returns a ``HandResult(success=False)`` rather than raising.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: int = 60) -> None:
        self._base_url = (base_url or settings.openfang_url).rstrip("/")
        self._timeout = timeout
        self._healthy = False
        self._last_health_check: float = 0.0
        self._health_cache_ttl = 30.0  # seconds
        logger.info("OpenFangClient initialised → %s", self._base_url)

    # ── Health ───────────────────────────────────────────────────────────────

    @property
    def healthy(self) -> bool:
        """Cached health check — hits /health at most once per TTL."""
        now = time.time()
        if now - self._last_health_check > self._health_cache_ttl:
            self._healthy = self._check_health()
            self._last_health_check = now
        return self._healthy

    def _check_health(self) -> bool:
        try:
            import urllib.request

            req = urllib.request.Request(
                f"{self._base_url}/health",
                method="GET",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as exc:
            logger.debug("OpenFang health check failed: %s", exc)
            return False

    # ── Hand execution ───────────────────────────────────────────────────────

    async def execute_hand(
        self,
        hand: str,
        params: dict[str, Any],
        timeout: Optional[int] = None,
    ) -> HandResult:
        """Execute an OpenFang Hand and return the result.

        Args:
            hand: Hand name (browser, collector, predictor, etc.)
            params: Parameters for the hand (task-specific)
            timeout: Override default timeout for long-running hands

        Returns:
            HandResult with output or error details.
        """
        if hand not in OPENFANG_HANDS:
            return HandResult(
                hand=hand,
                success=False,
                error=f"Unknown hand: {hand}. Available: {', '.join(OPENFANG_HANDS)}",
            )

        start = time.time()
        try:
            import json
            import urllib.request

            payload = json.dumps({"hand": hand, "params": params}).encode()
            req = urllib.request.Request(
                f"{self._base_url}/api/v1/hands/{hand}/execute",
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            effective_timeout = timeout or self._timeout
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                body = json.loads(resp.read().decode())
                latency = (time.time() - start) * 1000

                return HandResult(
                    hand=hand,
                    success=body.get("success", True),
                    output=body.get("output", body.get("result", "")),
                    latency_ms=latency,
                    metadata=body.get("metadata", {}),
                )

        except Exception as exc:
            latency = (time.time() - start) * 1000
            logger.warning(
                "OpenFang hand '%s' failed (%.0fms): %s",
                hand,
                latency,
                exc,
            )
            return HandResult(
                hand=hand,
                success=False,
                error=str(exc),
                latency_ms=latency,
            )

    # ── Convenience wrappers for common hands ────────────────────────────────

    async def browse(self, url: str, instruction: str = "") -> HandResult:
        """Web automation via OpenFang's Browser hand."""
        return await self.execute_hand(
            "browser", {"url": url, "instruction": instruction}
        )

    async def collect(self, target: str, depth: str = "shallow") -> HandResult:
        """OSINT collection via OpenFang's Collector hand."""
        return await self.execute_hand(
            "collector", {"target": target, "depth": depth}
        )

    async def predict(self, question: str, horizon: str = "1w") -> HandResult:
        """Superforecasting via OpenFang's Predictor hand."""
        return await self.execute_hand(
            "predictor", {"question": question, "horizon": horizon}
        )

    async def find_leads(self, icp: str, max_results: int = 10) -> HandResult:
        """Prospect discovery via OpenFang's Lead hand."""
        return await self.execute_hand(
            "lead", {"icp": icp, "max_results": max_results}
        )

    async def research(self, topic: str, depth: str = "standard") -> HandResult:
        """Deep research via OpenFang's Researcher hand."""
        return await self.execute_hand(
            "researcher", {"topic": topic, "depth": depth}
        )

    # ── Inventory ────────────────────────────────────────────────────────────

    async def list_hands(self) -> list[dict]:
        """Query OpenFang for its available hands and their status."""
        try:
            import json
            import urllib.request

            req = urllib.request.Request(
                f"{self._base_url}/api/v1/hands",
                method="GET",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            logger.debug("Failed to list OpenFang hands: %s", exc)
            return []

    def status(self) -> dict:
        """Return a status summary for the dashboard."""
        return {
            "url": self._base_url,
            "healthy": self.healthy,
            "available_hands": list(OPENFANG_HANDS),
        }


# ── Module-level singleton ──────────────────────────────────────────────────
openfang_client = OpenFangClient()
