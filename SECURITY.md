# ADR Tool API - Security Implementation Guide

This document describes the authentication and CORS security implementation for the ADR Tool API.

## ⚠️ Security Remediation (v2) - Resolved Issues

The following security issues have been addressed in this version:

### 1. ✅ Hardcoded API Key Removed
- **Previous issue**: Hardcoded test API key `test-api-key-12345` was valid in production
- **Fix**: API keys must now be configured via `VALID_API_KEYS` environment variable only
- No hardcoded keys exist in source code

### 2. ✅ SECRET_KEY Single Source of Truth
- **Previous issue**: SECRET_KEY was defined in both `config.py` and `security.py`
- **Fix**: `config.py` now imports SECRET_KEY from `security.py` - single source of truth
- Production deployments must set `SECRET_KEY` environment variable

### 3. ✅ Authentication Tests Fixed
- **Previous issue**: Tests used non-existent mock credentials
- **Fix**: Tests now use correct mock users (`admin`/`user`/`reader` with `password123`)
- All 13 security tests now pass

---

## Overview

The ADR Tool API implements robust security measures suitable for Vincent's security review:

1. **Dual Authentication**: API Keys + OAuth2/JWT
2. **Strict CORS**: Explicit origin allowlist only
3. **Role-Based Access Control (RBAC)** via scopes
4. **Security Headers**: CSP, X-Frame-Options, etc.

---

## Authentication

### Method 1: OAuth2 JWT Tokens (Recommended)

#### Login
```bash
curl -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_username&password=your_password&scope=adr:read+adr:write"
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800,
  "scopes": ["adr:read", "adr:write"]
}
```

#### Use the Token
```bash
curl -X GET "http://localhost:8000/api/v1/adrs" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

#### Refresh Token
```bash
curl -X POST "http://localhost:8000/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGciOiJIUzI1NiIs..."}'
```

### Method 2: API Keys

#### Create API Key (requires admin:settings scope)
```bash
curl -X POST "http://localhost:8000/api/v1/auth/api-key" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-api-key", "scopes": ["adr:read", "adr:write"]}'
```

Response (key shown only once):
```json
{
  "id": "uuid-here",
  "name": "my-api-key",
  "key": "adr_ABC123...",
  "scopes": ["adr:read", "adr:write"],
  "created_at": "2024-01-01T00:00:00"
}
```

#### Use API Key
```bash
curl -X GET "http://localhost:8000/api/v1/adrs" \
  -H "X-API-Key: adr_ABC123..."
```

---

## Scopes

| Scope | Description |
|-------|-------------|
| `adr:read` | Read ADR records |
| `adr:write` | Create and update ADRs |
| `adr:delete` | Delete ADRs |
| `admin:users` | Manage users |
| `admin:settings` | Manage API settings |

---

## CORS Configuration

### Strict CORS Policy

The API enforces strict CORS:

1. **Explicit Origin Allowlist**: Only configured origins are allowed
2. **No Wildcards**: Never use `*` in production
3. **Restricted Methods**: Only GET, POST, PUT, PATCH, DELETE, OPTIONS
4. **Restricted Headers**: Only necessary headers allowed
5. **Preflight Caching**: 10 minutes for performance

### Configuration

Set allowed origins via environment variable:

```bash
# .env file
ALLOWED_ORIGINS=https://your-domain.com,https://admin.your-domain.com
```

### Development vs Production

- **Development**: Automatically allows `localhost:3000`, `localhost:8000`
- **Production**: No origins allowed unless explicitly configured

---

## Environment Variables

**⚠️ CRITICAL**: Never commit actual secrets to version control. Use environment variables or a secrets manager.

Create a `.env` file (add to `.gitignore`):

```bash
# SECURITY - REQUIRED IN PRODUCTION
# Generate with: openssl rand -hex 32
SECRET_KEY=your-very-long-random-secret-key

# Algorithm for JWT signing (default: HS256)
ALGORITHM=HS256

# Token expiration (default: 30 minutes)
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS (comma-separated) - STRICT: only configure allowed origins
ALLOWED_ORIGINS=https://your-domain.com,https://admin.your-domain.com

# API Keys (comma-separated) - REQUIRED for API key authentication
# Format: key1,key2,key3
VALID_API_KEYS=your-api-key-1,your-api-key-2

# Application
APP_NAME=ADR Tool API
DEBUG=false
```

### Security Variables Checklist

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | **Yes** | JWT signing key - must be random and secure |
| `VALID_API_KEYS` | For API key auth | Comma-separated list of valid API keys |
| `ALLOWED_ORIGINS` | For CORS | Comma-separated list of allowed origins |

---

## Running the Server

### Development
```bash
cd adr-tool-api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Production
```bash
# Set production environment
export ENVIRONMENT=production
export SECRET_KEY=$(openssl rand -hex 32)

# Run with production settings
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Security Headers

The API adds these security headers to all responses:

- `X-Frame-Options: DENY` - Prevents clickjacking
- `X-Content-Type-Options: nosniff` - Prevents MIME sniffing
- `Content-Security-Policy` - Restricts resource loading
- `Referrer-Policy: strict-origin-when-cross-origin` - Controls referrer
- `Permissions-Policy` - Disables dangerous features

---

## Testing Authentication

### Test with curl

```bash
# 1. Login
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=password123" | jq -r '.access_token')

# 2. Use token
curl -X GET "http://localhost:8000/api/v1/adrs" \
  -H "Authorization: Bearer $TOKEN"

# 3. Test API key (must be configured via VALID_API_KEYS environment variable)
curl -X GET "http://localhost:8000/api/v1/adrs" \
  -H "X-API-Key: your-configured-api-key"
```

### Test with Swagger UI

Visit `http://localhost:8000/docs` for interactive API documentation.

---

## Security Checklist for Vincent's Review

### Resolved Issues (v2)
- [x] ~~Hardcoded test API key removed~~ - API keys now must be configured via environment
- [x] ~~SECRET_KEY duplicated in config.py and security.py~~ - Single source of truth established
- [x] ~~Security tests using wrong credentials~~ - Fixed to use correct mock users

### Authentication & Tokens
- [x] JWT tokens with expiration
- [x] Refresh tokens for session continuity
- [x] API Key authentication option (env-only, no hardcoded keys)
- [x] Strict CORS (no wildcards)
- [x] Security headers (CSP, X-Frame-Options)
- [x] Role-based access control via scopes
- [x] Request ID tracking for audit
- [x] Token type validation (access vs refresh)
- [x] No credentials in URLs
- [x] HTTPS requirement documented

---

## Questions?

For security concerns or questions, review the source code in:
- `app/core/security.py` - Authentication logic
- `app/core/cors.py` - CORS configuration
- `app/api/auth.py` - Auth endpoints
