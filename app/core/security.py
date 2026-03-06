"""
Security configuration for ADR Tool API.
Provides API Key and OAuth2 JWT authentication with strict CORS policies.
"""
import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer, SecurityScopes
from jose import JWTError, jwt
from pydantic import BaseModel

# ============================================================================
# Configuration
# ============================================================================

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_IN_PRODUCTION_USE_STRONG_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# API Key Configuration
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_NAME = os.getenv("API_KEY_NAME", "adr-tool-api-key")

# CORS Configuration - STRICT: Only allow specific origins
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://your-domain.com,https://admin.your-domain.com"
).split(",")

ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()]

# Allow credentials
ALLOW_CREDENTIALS = True

# Strict CORS: Only allow these specific HTTP methods
ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

# Strict CORS: Only allow these headers
ALLOWED_HEADERS = [
    "Accept",
    "Accept-Language",
    "Content-Type",
    "Authorization",
    "X-API-Key",
    "X-Requested-With",
]

# Expose headers (what the client can see)
EXPOSE_HEADERS = ["X-Request-ID", "X-RateLimit-Remaining"]

# OAuth2 scopes
SCOPES = {
    "adr:read": "Read ADR records",
    "adr:write": "Create and update ADR records",
    "adr:delete": "Delete ADR records",
    "admin:users": "Manage users",
    "admin:settings": "Manage API settings",
}

# ============================================================================
# Models
# ============================================================================

class Token(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    scopes: List[str]


class TokenData(BaseModel):
    """Decoded token data"""
    sub: str  # subject (user_id)
    scopes: List[str] = []
    exp: Optional[datetime] = None


class User(BaseModel):
    """User model"""
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    disabled: bool = False
    scopes: List[str] = []


class APIKey(BaseModel):
    """API Key model"""
    id: str
    name: str
    key_hash: str
    scopes: List[str]
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    is_active: bool = True


# ============================================================================
# Password Hashing (using bcrypt via passlib)
# ============================================================================

from passlib.context import CryptContext

# Configure bcrypt context for password hashing
# Uses bcrypt as the hashing algorithm with appropriate rounds
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a bcrypt hash.
    
    Args:
        plain_password: The plain text password to verify
        hashed_password: The bcrypt hash to verify against
        
    Returns:
        True if password matches, False otherwise
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # If hash is malformed or other error, return False
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: The plain text password to hash
        
    Returns:
        The bcrypt hash of the password
    """
    return pwd_context.hash(password)


# ============================================================================
# JWT Token Handling
# ============================================================================

def create_access_token(data: dict, scopes: List[str], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "scopes": scopes,
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, scopes: Optional[List[str]] = None) -> str:
    """
    Create a JWT refresh token.
    
    Args:
        data: Dictionary with token data (e.g., {"sub": "username"})
        scopes: Optional list of scopes to preserve in the token for refresh
        
    Returns:
        Encoded JWT refresh token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
        # Store scopes in refresh token to preserve them on refresh
        "scopes": scopes or []
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Verify it's an access token
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        scopes = payload.get("scopes", [])
        
        return TokenData(sub=sub, scopes=scopes, exp=datetime.fromtimestamp(payload.get("exp", 0)))
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ============================================================================
# Authentication Dependencies
# ============================================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    scopes=SCOPES,
    auto_error=False
)


async def get_current_user(
    security: SecurityScopes,
    token: str = Depends(oauth2_scheme),
    api_key: str = Depends(API_KEY_HEADER)
) -> User:
    """
    Get current authenticated user via OAuth2 token or API Key.
    Supports both authentication methods.
    """
    # Try OAuth2 token first
    if token:
        return await get_user_from_token(security, token)
    
    # Try API Key
    if api_key:
        return await get_user_from_api_key(security, api_key)
    
    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={
            "WWW-Authenticate": "Bearer",
            "X-API-Key": 'realm="api"',
        },
    )


async def get_user_from_token(security: SecurityScopes, token: str) -> User:
    """Validate OAuth2 JWT token and return user"""
    token_data = decode_token(token)
    
    # Check token expiration
    if token_data.exp and token_data.exp < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check required scopes
    for scope in security.scopes:
        if scope not in token_data.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not enough permissions. Required scope: {scope}",
            )
    
    # In production, fetch user from database
    # For now, return a mock user
    user = User(
        id=token_data.sub,
        username=token_data.sub,
        email=f"{token_data.sub}@example.com",
        scopes=token_data.scopes,
    )
    
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    return user


async def get_user_from_api_key(security: SecurityScopes, api_key: str) -> User:
    """Validate API Key and return user"""
    # In production, look up API key in database
    # For demo, check against environment variable
    valid_api_keys = os.getenv("VALID_API_KEYS", "").split(",")
    valid_api_keys = [k.strip() for k in valid_api_keys if k.strip()]
    
    # SECURITY FIX: Never allow hardcoded test API keys in source code
    # API keys must be configured via VALID_API_KEYS environment variable
    # This prevents accidental exposure of test credentials in production
    
    if api_key not in valid_api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"X-API-Key": 'realm="api"'},
        )
    
    # Check required scopes for API key
    # API keys have all permissions in this implementation
    # In production, store scopes with the API key
    
    user = User(
        id="api-key-user",
        username="api-key-user",
        email="api-key@example.com",
        scopes=["adr:read", "adr:write", "adr:delete"],
    )
    
    return user


def require_scopes(required_scopes: List[str]):
    """Dependency to require specific scopes"""
    async def scope_checker(user: User = Depends(get_current_user)) -> User:
        for scope in required_scopes:
            if scope not in user.scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Not authorized. Required: {scope}",
                )
        return user
    return scope_checker
