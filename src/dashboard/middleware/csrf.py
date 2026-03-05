"""CSRF protection middleware for FastAPI.

Provides CSRF token generation, validation, and middleware integration
to protect state-changing endpoints from cross-site request attacks.
"""

import secrets
import hmac
import hashlib
from typing import Callable, Optional
from functools import wraps

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse


# Module-level set to track exempt routes
_exempt_routes: set[str] = set()


def csrf_exempt(endpoint: Callable) -> Callable:
    """Decorator to mark an endpoint as exempt from CSRF validation.
    
    Usage:
        @app.post("/webhook")
        @csrf_exempt
        def webhook_endpoint():
            ...
    """
    @wraps(endpoint)
    async def async_wrapper(*args, **kwargs):
        return await endpoint(*args, **kwargs)
    
    @wraps(endpoint)
    def sync_wrapper(*args, **kwargs):
        return endpoint(*args, **kwargs)
    
    # Mark the original function as exempt
    endpoint._csrf_exempt = True  # type: ignore
    
    # Also mark the wrapper
    if hasattr(endpoint, '__code__') and endpoint.__code__.co_flags & 0x80:
        async_wrapper._csrf_exempt = True  # type: ignore
        return async_wrapper
    else:
        sync_wrapper._csrf_exempt = True  # type: ignore
        return sync_wrapper


def is_csrf_exempt(endpoint: Callable) -> bool:
    """Check if an endpoint is marked as CSRF exempt."""
    return getattr(endpoint, '_csrf_exempt', False)


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token.
    
    Returns:
        A secure random token string.
    """
    return secrets.token_urlsafe(32)


def validate_csrf_token(token: str, expected_token: str) -> bool:
    """Validate a CSRF token against the expected token.
    
    Uses constant-time comparison to prevent timing attacks.
    
    Args:
        token: The token provided by the client.
        expected_token: The expected token (from cookie/session).
        
    Returns:
        True if the token is valid, False otherwise.
    """
    if not token or not expected_token:
        return False
    
    return hmac.compare_digest(token, expected_token)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce CSRF protection on state-changing requests.
    
    Safe methods (GET, HEAD, OPTIONS, TRACE) are allowed without CSRF tokens.
    State-changing methods (POST, PUT, DELETE, PATCH) require a valid CSRF token.
    
    The token is expected to be:
    - In the X-CSRF-Token header, or
    - In the request body as 'csrf_token', or
    - Matching the token in the csrf_token cookie
    
    Usage:
        app.add_middleware(CSRFMiddleware, secret="your-secret-key")
    
    Attributes:
        secret: Secret key for token signing (optional, for future use).
        cookie_name: Name of the CSRF cookie.
        header_name: Name of the CSRF header.
        safe_methods: HTTP methods that don't require CSRF tokens.
    """
    
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    
    def __init__(
        self,
        app,
        secret: Optional[str] = None,
        cookie_name: str = "csrf_token",
        header_name: str = "X-CSRF-Token",
        form_field: str = "csrf_token"
    ):
        super().__init__(app)
        self.secret = secret
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.form_field = form_field
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process the request and enforce CSRF protection.
        
        For safe methods: Set a CSRF token cookie if not present.
        For unsafe methods: Validate the CSRF token.
        """
        # Bypass CSRF if explicitly disabled (e.g. in tests)
        import os
        if os.environ.get("TIMMY_DISABLE_CSRF") == "1":
            return await call_next(request)

        # Get existing CSRF token from cookie
        csrf_cookie = request.cookies.get(self.cookie_name)
        
        # For safe methods, just ensure a token exists
        if request.method in self.SAFE_METHODS:
            response = await call_next(request)
            
            # Set CSRF token cookie if not present
            if not csrf_cookie:
                new_token = generate_csrf_token()
                response.set_cookie(
                    key=self.cookie_name,
                    value=new_token,
                    httponly=False,  # Must be readable by JavaScript
                    secure=False,    # Set to True in production with HTTPS
                    samesite="Lax",
                    max_age=86400    # 24 hours
                )
            
            return response
        
        # For unsafe methods, check if route is exempt first
        # Note: We need to let the request proceed and check at response time
        # since FastAPI routes are resolved after middleware
        
        # Try to validate token early
        if not await self._validate_request(request, csrf_cookie):
            # Check if this might be an exempt route by checking path patterns
            # that are commonly exempt (like webhooks)
            path = request.url.path
            if not self._is_likely_exempt(path):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "CSRF validation failed",
                        "code": "CSRF_INVALID",
                        "message": "Missing or invalid CSRF token. Include the token from the csrf_token cookie in the X-CSRF-Token header or as a form field."
                    }
                )
        
        return await call_next(request)
    
    def _is_likely_exempt(self, path: str) -> bool:
        """Check if a path is likely to be CSRF exempt.
        
        Common patterns like webhooks, API endpoints, etc.
        
        Args:
            path: The request path.
            
        Returns:
            True if the path is likely exempt.
        """
        exempt_patterns = [
            "/webhook",
            "/api/v1/",
            "/lightning/webhook",
            "/_internal/",
        ]
        return any(pattern in path for pattern in exempt_patterns)
    
    async def _validate_request(self, request: Request, csrf_cookie: Optional[str]) -> bool:
        """Validate the CSRF token in the request.
        
        Checks for token in:
        1. X-CSRF-Token header
        2. csrf_token form field
        
        Args:
            request: The incoming request.
            csrf_cookie: The expected token from the cookie.
            
        Returns:
            True if the token is valid, False otherwise.
        """
        # Validate against cookie
        if not csrf_cookie:
            return False

        # Get token from header
        header_token = request.headers.get(self.header_name)
        if header_token and validate_csrf_token(header_token, csrf_cookie):
            return True
        
        # If no header token, try form data (for non-JSON POSTs)
        # Check Content-Type to avoid hanging on non-form requests
        content_type = request.headers.get("Content-Type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            try:
                form_data = await request.form()
                form_token = form_data.get(self.form_field)
                if form_token and validate_csrf_token(str(form_token), csrf_cookie):
                    return True
            except Exception:
                # Error parsing form data, treat as invalid
                pass
        
        return False
