"""
ADR Tool API - FastAPI application with robust authentication and CORS.
"""
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uuid
import time

from app.core.config import settings
from app.core.cors import SecurityHeadersMiddleware, setup_cors

# Gate /docs and /redoc: only available in development
_is_dev = os.getenv("ENVIRONMENT", "development") == "development"

# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Secure REST API for managing Architecture Decision Records.",
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)

# Setup CORS (before routes)
setup_cors(app)

# Add security headers
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# =============================================================================
# Request ID Middleware
# =============================================================================

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request ID to each request"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    return response


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "timestamp": time.time()
    }


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": getattr(request.state, "request_id", None)
        }
    )


# =============================================================================
# Import and Register Routes
# =============================================================================

from app.api import auth, adrs, ai_generate

app.include_router(auth.router, prefix="/api/v1")
app.include_router(adrs.router, prefix="/api/v1")
app.include_router(ai_generate.router, prefix="/api/v1")


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }
