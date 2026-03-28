"""
Learnings API — CRUD endpoints for organizational memory extracted from user corrections.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.security import User, require_scopes
from app.db.adr_store import (
    list_learnings as db_list,
    get_learning as db_get,
    get_learning_stats as db_stats,
    update_learning as db_update,
    deactivate_learning as db_deactivate,
)

router = APIRouter(prefix="/learnings", tags=["Learnings"])


class LearningUpdate(BaseModel):
    confidence: Optional[float] = None
    active: Optional[int] = None


@router.get("")
async def list_learnings(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_scopes(["adr:read"])),
):
    """List learnings ranked by confidence x recency."""
    offset = (page - 1) * page_size
    items, total = db_list(limit=page_size, offset=offset)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (offset + page_size) < total,
        "has_prev": page > 1,
    }


@router.get("/stats")
async def learning_stats(
    user: User = Depends(require_scopes(["adr:read"])),
):
    """Get learning statistics: totals by category, avg confidence."""
    return db_stats()


@router.put("/{learning_id}")
async def update_learning(
    learning_id: str,
    data: LearningUpdate,
    user: User = Depends(require_scopes(["adr:write"])),
):
    """Update a learning's confidence or active status."""
    existing = db_get(learning_id)
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Learning '{learning_id}' not found")
    fields = data.model_dump(exclude_unset=True)
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        return existing
    db_update(learning_id, **fields)
    return db_get(learning_id)


@router.delete("/{learning_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_learning(
    learning_id: str,
    user: User = Depends(require_scopes(["adr:write"])),
):
    """Soft-delete a learning (set active=0)."""
    existing = db_get(learning_id)
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Learning '{learning_id}' not found")
    db_deactivate(learning_id)
    return None
