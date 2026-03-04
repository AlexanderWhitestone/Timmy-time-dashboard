"""Security headers middleware for FastAPI.

Adds common security headers to all HTTP responses to improve
application security posture against various attacks.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses.
    
    Adds the following headers:
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking
    - X-XSS-Protection: Enables browser XSS filter
    - Referrer-Policy: Controls referrer information
    - Permissions-Policy: Restricts feature access
    - Content-Security-Policy: Mitigates XSS and data injection
    - Strict-Transport-Security: Enforces HTTPS (production only)
    
    Usage:
        app.add_middleware(SecurityHeadersMiddleware)
        
        # Or with production settings:
        app.add_middleware(SecurityHeadersMiddleware, production=True)
    
    Attributes:
        production: If True, adds HSTS header for HTTPS enforcement.
        csp_report_only: If True, sends CSP in report-only mode.
    """
    
    def __init__(
        self,
        app,
        production: bool = False,
        csp_report_only: bool = False,
        custom_csp: str = None
    ):
        super().__init__(app)
        self.production = production
        self.csp_report_only = csp_report_only
        
        # Build CSP directive
        self.csp_directive = custom_csp or self._build_csp()
    
    def _build_csp(self) -> str:
        """Build the Content-Security-Policy directive.
        
        Creates a restrictive default policy that allows:
        - Same-origin resources by default
        - Inline scripts/styles (needed for HTMX/Bootstrap)
        - Data URIs for images
        - WebSocket connections
        
        Returns:
            CSP directive string.
        """
        directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.jsdelivr.net",  # HTMX needs inline
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com cdn.jsdelivr.net",  # Bootstrap needs inline
            "img-src 'self' data: blob:",
            "font-src 'self' fonts.gstatic.com",
            "connect-src 'self' ws: wss:",  # WebSocket support
            "media-src 'self'",
            "object-src 'none'",
            "frame-src 'none'",
            "frame-ancestors 'self'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        return "; ".join(directives)
    
    def _add_security_headers(self, response: Response) -> None:
        """Add security headers to a response.
        
        Args:
            response: The response to add headers to.
        """
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        
        # Enable XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Restrict browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), "
            "microphone=(), "
            "geolocation=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )
        
        # Content Security Policy
        csp_header = "Content-Security-Policy-Report-Only" if self.csp_report_only else "Content-Security-Policy"
        response.headers[csp_header] = self.csp_directive
        
        # HTTPS enforcement (production only)
        if self.production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to the response.
        
        Args:
            request: The incoming request.
            call_next: Callable to get the response from downstream.
            
        Returns:
            Response with security headers added.
        """
        try:
            response = await call_next(request)
            self._add_security_headers(response)
            return response
        except Exception:
            # Create a response for the error with security headers
            from starlette.responses import PlainTextResponse
            response = PlainTextResponse(
                content="Internal Server Error",
                status_code=500
            )
            self._add_security_headers(response)
            # Return the error response with headers (don't re-raise)
            return response
