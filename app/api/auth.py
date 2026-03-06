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
# Mock User Database (In Production, replace with real database)
# =============================================================================
# Users are stored as: username -> {password_hash, scopes}
# Password hashes are bcrypt hashes generated using bcrypt.hashpw()
# 
# Demo users (password: "password123"):
# - admin: has all adr scopes + admin scopes
# - user: has read/write scopes
# - reader: has read-only scope
#
# NOTE: bcrypt hash regenerated for compatibility with bcrypt 4.x

MOCK_USERS_DB = {
    "admin": {
        # bcrypt hash of "password123"
        "password_hash": "$2b$12$TS9XMj7NlNPosO1M6.PU1e2T.o6haYEZMG04Hzc0859z3FIxwc.Xi",
        "scopes": ["adr:read", "adr:write", "adr:delete", "admin:users", "admin:settings"]
    },
    "user": {
        # bcrypt hash of "password123"
        "password_hash": "$2b$12$TS9XMj7NlNPosO1M6.PU1e2T.o6haYEZMG04Hzc0859z3FIxwc.Xi",
        "scopes": ["adr:read", "adr:write"]
    },
    "reader": {
        # bcrypt hash of "password123"
        "password_hash": "$2b$12$TS9XMj7NlNPosO1M6.PU1e2T.o6haYEZMG04Hzc0859z3FIxwc.Xi",
        "scopes": ["adr:read"]
    },
}


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    Authenticate a user with username and password.
    
    Uses passlib's bcrypt verify function for secure password verification.
    
    Args:
        username: The username to authenticate
        password: The plain text password to verify
        
    Returns:
        User data dict if authentication succeeds, None otherwise
    """
    user = MOCK_USERS_DB.get(username)
    if not user:
        return None
    
    # Use passlib's verify_password for secure bcrypt comparison
    if not verify_password(password, user["password_hash"]):
        return None
    
    return user


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    OAuth2 compatible token login endpoint.
    Use username as email and password for authentication.
    
    Scopes can be requested using the scope parameter (space-separated).
    Example: scope="adr:read adr:write"
    
    Demo credentials:
    - username: admin, password: password123 (full access)
    - username: user, password: password123 (read/write)
    - username: reader, password: password123 (read-only)
    """
    # Validate credentials using proper password verification
    user = authenticate_user(form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Parse requested scopes - validate against user's allowed scopes
    # form_data.scopes can be a string or list depending on FastAPI version
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
        expires_in=1800,  # 30 minutes in seconds
        scopes=valid_scopes
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(request: TokenRequest):
    """
    Refresh access token using a valid refresh token.
    
    Preserves the original scopes from the refresh token.
    """
    try:
        # Decode refresh token using centralized SECRET_KEY
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
        
        # SECURITY FIX: Preserve original scopes from refresh token
        # The refresh token now stores scopes at creation time
        scopes = payload.get("scopes", ["adr:read"])
        
        # Validate preserved scopes are still valid
        valid_scopes = [s for s in scopes if s in SCOPES]
        if not valid_scopes:
            valid_scopes = ["adr:read"]
        
        # Create new access token with preserved scopes
        access_token = create_access_token(
            data={"sub": sub},
            scopes=valid_scopes,
            expires_delta=timedelta(minutes=30)
        )
        
        return Token(
            access_token=access_token,
            refresh_token=request.refresh_token,  # Keep same refresh token
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
    """
    Get current authenticated user information.
    """
    return user


@router.post("/api-key", response_model=APIKeyResponse)
async def create_api_key(
    request: APIKeyCreate,
    user: User = Depends(require_scopes(["admin:settings"]))
):
    """
    Create a new API key. Requires admin:settings scope.
    """
    key_id = str(uuid.uuid4())
    api_key = f"adr_{secrets.token_urlsafe(32)}"
    
    # In production, hash and store in database
    # Store: key_id, key_hash, user_id, scopes, created_at
    
    return APIKeyResponse(
        id=key_id,
        name=request.name,
        key=api_key,
        scopes=request.scopes,
        created_at=datetime.utcnow().isoformat()
    )
