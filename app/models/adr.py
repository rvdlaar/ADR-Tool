"""
ADR (Architecture Decision Record) models.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class ADRStatus(str, Enum):
    """ADR status enumeration"""
    PROPOSED = "Proposed"
    ACCEPTED = "Accepted"
    DEPRECATED = "Deprecated"
    SUPERSEDED = "Superseded"
    REJECTED = "Rejected"


class ADRStatusChange(BaseModel):
    """Status change model"""
    from_status: ADRStatus
    to_status: ADRStatus
    changed_by: str
    changed_at: datetime = Field(default_factory=datetime.utcnow)
    reason: Optional[str] = None


class ADRContext(BaseModel):
    """Context section of an ADR"""
    historical_context: Optional[str] = None
    constraints: Optional[List[str]] = None
    assumptions: Optional[List[str]] = None


class ADRDecision(BaseModel):
    """Decision section of an ADR"""
    decision: str
    alternatives_considered: Optional[List[dict]] = None


class ADRConsequences(BaseModel):
    """Consequences section of an ADR"""
    positive: Optional[List[str]] = None
    negative: Optional[List[str]] = None
    neutral: Optional[List[str]] = None
    tradeoffs: Optional[List[str]] = None


class ADR(BaseModel):
    """Architecture Decision Record model"""
    id: str
    title: str
    status: ADRStatus = ADRStatus.PROPOSED
    
    # Content
    context: str
    decision: str
    consequences: str
    
    # Metadata
    author: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relations
    superseded_by: Optional[str] = None
    supersedes: Optional[List[str]] = None
    
    # Tags
    tags: List[str] = []
    
    # AI-specific
    ai_generated: bool = False
    ai_model: Optional[str] = None


class ADRCreate(BaseModel):
    """Schema for creating a new ADR"""
    title: str = Field(..., min_length=1, max_length=200)
    context: str = Field(..., min_length=10)
    decision: str = Field(..., min_length=10)
    consequences: str = Field(..., min_length=10)
    tags: List[str] = []
    
    # Optional: AI assistance
    ai_assist: bool = False


class ADRUpdate(BaseModel):
    """Schema for updating an ADR"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    context: Optional[str] = Field(None, min_length=10)
    decision: Optional[str] = Field(None, min_length=10)
    consequences: Optional[str] = Field(None, min_length=10)
    status: Optional[ADRStatus] = None
    tags: Optional[List[str]] = None
    superseded_by: Optional[str] = None


class ADRListResponse(BaseModel):
    """Paginated list of ADRs"""
    items: List[ADR]
    total: int
    page: int = 1
    page_size: int = 20
    has_next: bool = False
    has_prev: bool = False


class ADRSearchQuery(BaseModel):
    """Search query parameters"""
    q: Optional[str] = None
    status: Optional[ADRStatus] = None
    author: Optional[str] = None
    tags: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = 1
    page_size: int = 20
    sort_by: str = "created_at"
    sort_order: str = "desc"
