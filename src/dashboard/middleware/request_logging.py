"""Request logging middleware for FastAPI.

Logs HTTP requests with timing, status codes, and client information
for monitoring and debugging purposes.
"""

import time
import uuid
import logging
from typing import Optional, List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


logger = logging.getLogger("timmy.requests")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests.
    
    Logs the following information for each request:
    - HTTP method and path
    - Response status code
    - Request processing time
    - Client IP address
    - User-Agent header
    - Correlation ID for tracing
    
    Usage:
        app.add_middleware(RequestLoggingMiddleware)
        
        # Skip certain paths:
        app.add_middleware(RequestLoggingMiddleware, skip_paths=["/health", "/metrics"])
    
    Attributes:
        skip_paths: List of URL paths to skip logging.
        log_level: Logging level for successful requests.
    """
    
    def __init__(
        self,
        app,
        skip_paths: Optional[List[str]] = None,
        log_level: int = logging.INFO
    ):
        super().__init__(app)
        self.skip_paths = set(skip_paths or [])
        self.log_level = log_level
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Log the request and response details.
        
        Args:
            request: The incoming request.
            call_next: Callable to get the response from downstream.
            
        Returns:
            The response from downstream.
        """
        # Check if we should skip logging this path
        if request.url.path in self.skip_paths:
            return await call_next(request)
        
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())[:8]
        request.state.correlation_id = correlation_id
        
        # Record start time
        start_time = time.time()
        
        # Get client info
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "-")
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log the request
            self._log_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=correlation_id
            )
            
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            
            return response
            
        except Exception as exc:
            # Calculate duration even for failed requests
            duration_ms = (time.time() - start_time) * 1000

            # Log the error
            logger.error(
                f"[{correlation_id}] {request.method} {request.url.path} "
                f"- ERROR - {duration_ms:.2f}ms - {client_ip} - {str(exc)}"
            )

            # Auto-escalate: create bug report task from unhandled exception
            try:
                from infrastructure.error_capture import capture_error
                capture_error(
                    exc,
                    source="http",
                    context={
                        "method": request.method,
                        "path": request.url.path,
                        "correlation_id": correlation_id,
                        "client_ip": client_ip,
                        "duration_ms": f"{duration_ms:.0f}",
                    },
                )
            except Exception:
                pass  # never let escalation break the request

            # Re-raise the exception
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract the client IP address from the request.
        
        Checks X-Forwarded-For and X-Real-IP headers first for proxied requests,
        falls back to the direct client IP.
        
        Args:
            request: The incoming request.
            
        Returns:
            Client IP address string.
        """
        # Check for forwarded IP (behind proxy/load balancer)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, take the first one
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct connection
        if request.client:
            return request.client.host
        
        return "-"
    
    def _log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        client_ip: str,
        user_agent: str,
        correlation_id: str
    ) -> None:
        """Format and log the request details.
        
        Args:
            method: HTTP method.
            path: Request path.
            status_code: HTTP status code.
            duration_ms: Request duration in milliseconds.
            client_ip: Client IP address.
            user_agent: User-Agent header value.
            correlation_id: Request correlation ID.
        """
        # Determine log level based on status code
        level = self.log_level
        if status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400:
            level = logging.WARNING
        
        message = (
            f"[{correlation_id}] {method} {path} - {status_code} "
            f"- {duration_ms:.2f}ms - {client_ip}"
        )
        
        # Add user agent for non-health requests
        if path not in self.skip_paths:
            message += f" - {user_agent[:50]}"
        
        logger.log(level, message)
