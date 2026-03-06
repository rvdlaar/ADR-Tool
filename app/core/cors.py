"""
CORS Configuration for ADR Tool API.
Strict CORS policies for security.
"""
import os
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def get_cors_origins() -> List[str]:
    """
    Get allowed CORS origins from environment.
    For security, only explicitly allowed origins should be permitted.
    """
    env_origins = os.getenv("ALLOWED_ORIGINS", "")
    
    if not env_origins:
        # Default: no origins allowed in production
        return []
    
    origins = [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    return origins


def setup_cors(app: FastAPI) -> None:
    """
    Configure strict CORS policies for the ADR Tool API.
    
    Security measures:
    - Explicit list of allowed origins (no wildcards in production)
    - Strict HTTP methods
    - Strict headers
    - Credentials allowed only from verified origins
    - Preflight caching for performance
    """
    origins = get_cors_origins()
    
    # If no origins configured, warn in development
    if not origins:
        # Allow localhost for development only
        dev_origins = [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]
        
        environment = os.getenv("ENVIRONMENT", "development")
        if environment == "development":
            origins = dev_origins
            print("⚠️  CORS: Running in DEVELOPMENT mode - allowing localhost origins")
        else:
            print("⚠️  CORS: No allowed origins configured! API will reject all cross-origin requests.")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,  # Strict: only these origins
        allow_origin_regex=None,  # Disable regex matching for security
        allow_credentials=True,  # Allow cookies/auth headers
        allow_methods=[
            "GET",
            "POST", 
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ],  # Strict: only needed methods
        allow_headers=[
            "Accept",
            "Accept-Language", 
            "Content-Type",
            "Content-Language",
            "Authorization",
            "X-API-Key",
            "X-Request-ID",
            "X-Client-Version",
        ],  # Strict: only needed headers
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],  # Headers exposed to browser
        max_age=600,  # Cache preflight for 10 minutes (strict)
    )


# =============================================================================
# CORS Validation Helper
# =============================================================================

def validate_origin(origin: str, allowed_origins: List[str]) -> bool:
    """
    Validate if an origin is in the allowed list.
    Use this for custom validation logic if needed.
    """
    # Direct match
    if origin in allowed_origins:
        return True
    
    # In production, you might want more sophisticated validation
    # e.g., check against a list of allowed domains
    return False


# =============================================================================
# Security Headers Middleware
# =============================================================================

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    """
    
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        
        # Strict Transport Security (HSTS)
        # Uncomment in production with proper HTTPS
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # XSS Protection
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Content Security Policy - strict
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions Policy
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=()"
        )
        
        return response
