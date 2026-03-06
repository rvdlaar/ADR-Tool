"""
Pydantic schemas for API request/response models.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# =============================================================================
# ADR Schemas (imported from models)
# =============================================================================

from app.models.adr import ADRStatus


# =============================================================================
# AI Generation Schemas
# =============================================================================

class ADRGenerateRequest(BaseModel):
    """Request to generate an ADR using AI"""
    title: str = Field(..., min_length=3, max_length=200, description="Title for the ADR")
    description: str = Field(..., min_length=10, description="Description of the architectural decision")
    context: Optional[str] = Field(None, description="Additional context about the decision")
    requirements: Optional[List[str]] = Field(None, description="Requirements to consider")
    constraints: Optional[List[str]] = Field(None, description="Constraints to respect")
    alternatives: Optional[List[str]] = Field(None, description="Alternatives already considered")


class ADRGenerateResponse(BaseModel):
    """Response containing the generated ADR"""
    generated: bool = True
    adr: Dict[str, Any]
    model_used: str
    message: str = "ADR generated successfully"


class ADRListResponse(BaseModel):
    """Paginated list of ADRs"""
    items: List[Dict[str, Any]]
    total: int
    page: int = 1
    page_size: int = 20
    has_next: bool = False
    has_prev: bool = False
