"""
Authentication API endpoints.
Provides API Key and OAuth2 JWT token generation.
"""
import os
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from pydantic import BaseModel

from app.core.security import (
    SCOPES,
    SECRET_KEY,
    ALGORITHM,
    Token,
    User,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    get_password_hash,
    require_scopes,
    verify_password,
)
from app.core.user_store import authenticate_user

router = APIRouter(prefix="/auth", tags=["authentication"])


# =============================================================================
# Models
# =============================================================================

class TokenRequest(BaseModel):
    """Request new access token using refresh token"""
    refresh_token: str


class APIKeyCreate(BaseModel):
    """Request to create an API key"""
    name: str
    scopes: list[str] = ["adr:read"]


class APIKeyResponse(BaseModel):
    """API key response (key shown only once)"""
    id: str
    name: str
    key: str  # Only shown on creation
    scopes: list[str]
    created_at: str


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    OAuth2 compatible token login endpoint.
    Use username and password for authentication.

    Scopes can be requested using the scope parameter (space-separated).
    Example: scope="adr:read adr:write"
    """
    # Validate credentials using SQLite-backed user store
    user = authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Parse requested scopes - validate against user's allowed scopes
    if isinstance(form_data.scopes, list):
        requested_scopes = form_data.scopes
    elif isinstance(form_data.scopes, str) and form_data.scopes:
        requested_scopes = form_data.scopes.split()
    else:
        requested_scopes = []

    # Filter to only scopes the user is allowed to have
    valid_scopes = []
    user_allowed_scopes = user.get("scopes", ["adr:read"])
    for scope in requested_scopes:
        if scope in SCOPES and scope in user_allowed_scopes:
            valid_scopes.append(scope)

    # If no scopes requested or invalid, grant user's default scopes
    if not valid_scopes:
        valid_scopes = user_allowed_scopes[:1] if user_allowed_scopes else ["adr:read"]

    # Create tokens with authenticated user's subject
    token_data = {"sub": form_data.username}

    access_token = create_access_token(
        data=token_data,
        scopes=valid_scopes,
        expires_delta=timedelta(minutes=30)
    )

    # Create refresh token with original scopes embedded
    refresh_token = create_refresh_token(
        data={**token_data, "scopes": valid_scopes}
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=1800,
        scopes=valid_scopes
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(request: TokenRequest):
    """
    Refresh access token using a valid refresh token.
    Preserves the original scopes from the refresh token.
    """
    try:
        payload = jwt.decode(
            request.refresh_token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        scopes = payload.get("scopes", ["adr:read"])
        valid_scopes = [s for s in scopes if s in SCOPES]
        if not valid_scopes:
            valid_scopes = ["adr:read"]

        access_token = create_access_token(
            data={"sub": sub},
            scopes=valid_scopes,
            expires_delta=timedelta(minutes=30)
        )

        return Token(
            access_token=access_token,
            refresh_token=request.refresh_token,
            token_type="bearer",
            expires_in=1800,
            scopes=valid_scopes
        )

    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@router.get("/me", response_model=User)
async def get_current_user_info(
    user: User = Depends(get_current_user)
):
    """Get current authenticated user information."""
    return user


@router.post("/api-key", response_model=APIKeyResponse)
async def create_api_key(
    request: APIKeyCreate,
    user: User = Depends(require_scopes(["admin:settings"]))
):
    """Create a new API key. Requires admin:settings scope."""
    key_id = str(uuid.uuid4())
    api_key = f"adr_{secrets.token_urlsafe(32)}"

    return APIKeyResponse(
        id=key_id,
        name=request.name,
        key=api_key,
        scopes=request.scopes,
        created_at=datetime.utcnow().isoformat()
    )
