"""
Pydantic schemas for API request/response models.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.models.adr import ADRStatus


class ADRGenerateRequest(BaseModel):
    """Request to generate an ADR using AI"""
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    context: Optional[str] = None
    requirements: Optional[List[str]] = None
    constraints: Optional[List[str]] = None
    alternatives: Optional[List[str]] = None
    # Extended fields
    decision_drivers: Optional[List[str]] = Field(None, description="Why is this decision happening now?")
    impacted_roles: Optional[List[str]] = Field(None, description="Roles affected by this decision")
    success_criteria: Optional[List[str]] = Field(None, description="How will we know this worked?")
    timeline: Optional[str] = Field(None, description="Reversibility window / commitment timeline")
    scope: Optional[str] = Field(None, description="What this decision covers and doesn't cover")
    profile: str = Field("detailed", description="'detailed' for senior architects, 'guided' for mid-level devs")


class ADRGenerateResponse(BaseModel):
    """Response containing the generated ADR with validation and conflicts"""
    generated: bool = True
    adr: Dict[str, Any]
    validation: Optional[Dict[str, Any]] = None
    conflicts: list = []
    conflict_warning: Optional[str] = None
    rag_context_used: bool = False
    related_adrs: list = []
    model_used: str = ""
    profile: str = "detailed"
    review_required: bool = True
    message: str = ""


class ADRListResponse(BaseModel):
    """Paginated list of ADRs"""
    items: List[Dict[str, Any]]
    total: int
    page: int = 1
    page_size: int = 20
    has_next: bool = False
    has_prev: bool = False
