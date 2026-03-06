"""
ADR (Architecture Decision Records) API endpoints.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.security import User, get_current_user, require_scopes
from app.models.adr import (
    ADR,
    ADRCreate,
    ADRListResponse,
    ADRStatus,
    ADRUpdate,
    ADRSearchQuery,
)

router = APIRouter(prefix="/adrs", tags=["ADR"])

# In-memory storage for demo (replace with database in production)
_adrs_db: dict[str, ADR] = {}


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=ADRListResponse)
async def list_adrs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[ADRStatus] = Query(None, alias="status"),
    author: Optional[str] = None,
    tags: Optional[str] = None,
    search: Optional[str] = None,
    user: User = Depends(require_scopes(["adr:read"]))
):
    """
    List all ADRs with optional filtering and pagination.
    Requires adr:read scope.
    """
    adrs = list(_adrs_db.values())
    
    # Apply filters
    if status_filter:
        adrs = [adr for adr in adrs if adr.status == status_filter]
    
    if author:
        adrs = [adr for adr in adrs if author.lower() in adr.author.lower()]
    
    if tags:
        tag_list = [t.strip().lower() for t in tags.split(",")]
        adrs = [adr for adr in adrs if any(t in [tg.lower() for tg in adr.tags] for t in tag_list)]
    
    if search:
        search_lower = search.lower()
        adrs = [
            adr for adr in adrs
            if search_lower in adr.title.lower()
            or search_lower in adr.context.lower()
            or search_lower in adr.decision.lower()
        ]
    
    # Sort by created_at descending
    adrs.sort(key=lambda x: x.created_at, reverse=True)
    
    # Paginate
    total = len(adrs)
    start = (page - 1) * page_size
    end = start + page_size
    items = adrs[start:end]
    
    return ADRListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=end < total,
        has_prev=page > 1
    )


@router.get("/{adr_id}", response_model=ADR)
async def get_adr(
    adr_id: str,
    user: User = Depends(require_scopes(["adr:read"]))
):
    """
    Get a specific ADR by ID.
    Requires adr:read scope.
    """
    adr = _adrs_db.get(adr_id)
    
    if not adr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ADR with id '{adr_id}' not found"
        )
    
    return adr


@router.post("", response_model=ADR, status_code=status.HTTP_201_CREATED)
async def create_adr(
    adr_data: ADRCreate,
    user: User = Depends(require_scopes(["adr:write"]))
):
    """
    Create a new ADR.
    Requires adr:write scope.
    """
    adr_id = str(uuid.uuid4())[:8]
    
    adr = ADR(
        id=adr_id,
        title=adr_data.title,
        context=adr_data.context,
        decision=adr_data.decision,
        consequences=adr_data.consequences,
        author=user.username,
        tags=adr_data.tags,
        status=ADRStatus.PROPOSED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    
    _adrs_db[adr_id] = adr
    
    return adr


@router.put("/{adr_id}", response_model=ADR)
async def update_adr(
    adr_id: str,
    adr_data: ADRUpdate,
    user: User = Depends(require_scopes(["adr:write"]))
):
    """
    Update an existing ADR.
    Requires adr:write scope.
    """
    if adr_id not in _adrs_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ADR with id '{adr_id}' not found"
        )
    
    adr = _adrs_db[adr_id]
    
    # Update fields
    update_data = adr_data.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if value is not None:
            setattr(adr, field, value)
    
    adr.updated_at = datetime.utcnow()
    _adrs_db[adr_id] = adr
    
    return adr


@router.patch("/{adr_id}/status", response_model=ADR)
async def update_adr_status(
    adr_id: str,
    new_status: ADRStatus,
    reason: Optional[str] = None,
    user: User = Depends(require_scopes(["adr:write"]))
):
    """
    Update ADR status (e.g., from Proposed to Accepted).
    Requires adr:write scope.
    """
    if adr_id not in _adrs_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ADR with id '{adr_id}' not found"
        )
    
    adr = _adrs_db[adr_id]
    old_status = adr.status
    adr.status = new_status
    adr.updated_at = datetime.utcnow()
    
    _adrs_db[adr_id] = adr
    
    return adr


@router.delete("/{adr_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_adr(
    adr_id: str,
    user: User = Depends(require_scopes(["adr:delete"]))
):
    """
    Delete an ADR.
    Requires adr:delete scope.
    """
    if adr_id not in _adrs_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ADR with id '{adr_id}' not found"
        )
    
    del _adrs_db[adr_id]
    
    return None


@router.get("/search/query", response_model=ADRListResponse)
async def search_adrs(
    query: ADRSearchQuery = Depends(),
    user: User = Depends(require_scopes(["adr:read"]))
):
    """
    Advanced search for ADRs.
    Requires adr:read scope.
    """
    return await list_adrs(
        page=query.page,
        page_size=query.page_size,
        status_filter=query.status,
        author=query.author,
        tags=",".join(query.tags) if query.tags else None,
        search=query.q,
        user=user
    )


@router.get("/stats/summary")
async def get_adr_stats(
    user: User = Depends(require_scopes(["adr:read"]))
):
    """
    Get ADR statistics summary.
    Requires adr:read scope.
    """
    adrs = list(_adrs_db.values())
    
    status_counts = {}
    for status in ADRStatus:
        count = sum(1 for adr in adrs if adr.status == status)
        status_counts[status.value] = count
    
    return {
        "total": len(adrs),
        "by_status": status_counts,
        "recent_count": sum(
            1 for adr in adrs
            if (datetime.utcnow() - adr.created_at).days < 30
        )
    }
