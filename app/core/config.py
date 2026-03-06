"""
Core configuration for ADR Tool API.

SECURITY: SECRET_KEY is sourced from security.py for single source of truth.
Do NOT define SECRET_KEY here - import it from app.core.security instead.
"""
from pydantic_settings import BaseSettings
from typing import List, Optional
import os

# Import SECRET_KEY from security.py for single source of truth
from app.core.security import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES


class Settings(BaseSettings):
    """Application settings"""
    
    # App
    APP_NAME: str = "ADR Tool API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Security - Now imported from security.py (single source of truth)
    # Removed duplicate SECRET_KEY definition
    
    # CORS - Comma-separated list of allowed origins
    ALLOWED_ORIGINS: str = ""
    
    # Database (placeholder)
    DATABASE_URL: Optional[str] = None
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
