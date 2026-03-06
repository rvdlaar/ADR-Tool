"""
ADR Tool API - FastAPI application with robust authentication and CORS.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uuid
import time

from app.core.config import settings
from app.core.cors import SecurityHeadersMiddleware, setup_cors

# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## ADR Tool API

A secure REST API for managing Architecture Decision Records (ADRs).

### Authentication

The API supports two authentication methods:

1. **OAuth2 JWT Tokens** (recommended)
   - Login with username/password to get access token
   - Use the access token in the Authorization header: `Bearer <token>`

2. **API Keys** (for server-to-server)
   - Create an API key via the admin endpoints
   - Use the API key in the X-API-Key header

### Scopes

- `adr:read` - Read ADR records
- `adr:write` - Create and update ADRs
- `adr:delete` - Delete ADRs
- `admin:users` - Manage users
- `admin:settings` - Manage API settings

### Security Features

- Strict CORS policies (only configured origins allowed)
- JWT access and refresh tokens
- API Key authentication
- Role-based access control via scopes
- Security headers (CSP, X-Frame-Options, etc.)
- Rate limiting (configurable)
""",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Setup CORS (before routes)
setup_cors(app)

# Add security headers
app.add_middleware(SecurityHeadersMiddleware)


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
