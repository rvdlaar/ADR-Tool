"""
ADR (Architecture Decision Records) API endpoints.
Persistent SQLite storage via adr_store.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import User, require_scopes
from app.models.adr import (
    ADR,
    ADRCreate,
    ADRListResponse,
    ADRStatus,
    ADRUpdate,
    ADRSearchQuery,
)
from app.db.adr_store import (
    create_adr as db_create,
    get_adr as db_get,
    list_adrs as db_list,
    update_adr as db_update,
    delete_adr as db_delete,
    get_stats as db_stats,
)

router = APIRouter(prefix="/adrs", tags=["ADR"])


def _index_adr_in_vector_store(adr: dict):
    """Best-effort embed and index an ADR in ChromaDB."""
    try:
        from app.services.embeddings import get_embedding_service
        from app.services.vector_store import get_vector_store, COLLECTION_ADRS
        vs = get_vector_store()
        if not vs:
            return
        text = f"{adr['title']}\n{adr.get('context', '')}\n{adr.get('decision', '')}"
        embedding = get_embedding_service().embed(text)
        vs.upsert(COLLECTION_ADRS, adr["id"], embedding, text, {
            "title": adr["title"],
            "status": adr.get("status", "Proposed"),
            "author": adr.get("author", ""),
        })
    except Exception:
        pass


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
    """List all ADRs with optional filtering and pagination."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    offset = (page - 1) * page_size
    items, total = db_list(
        limit=page_size, offset=offset,
        status=status_filter.value if status_filter else None,
        author=author, search=search, tags=tag_list
    )
    return ADRListResponse(
        items=[ADR(**_ensure_datetime(i)) for i in items],
        total=total, page=page, page_size=page_size,
        has_next=(offset + page_size) < total,
        has_prev=page > 1
    )


@router.get("/search/query", response_model=ADRListResponse)
async def search_adrs(
    query: ADRSearchQuery = Depends(),
    user: User = Depends(require_scopes(["adr:read"]))
):
    """Advanced search for ADRs."""
    return await list_adrs(
        page=query.page, page_size=query.page_size,
        status_filter=query.status, author=query.author,
        tags=",".join(query.tags) if query.tags else None,
        search=query.q, user=user
    )


@router.get("/stats/summary")
async def get_adr_stats(user: User = Depends(require_scopes(["adr:read"]))):
    """Get ADR statistics summary."""
    return db_stats()


@router.get("/{adr_id}", response_model=ADR)
async def get_adr(
    adr_id: str,
    user: User = Depends(require_scopes(["adr:read"]))
):
    """Get a specific ADR by ID."""
    adr = db_get(adr_id)
    if not adr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ADR '{adr_id}' not found")
    return ADR(**_ensure_datetime(adr))


@router.get("/{adr_id}/similar")
async def find_similar(
    adr_id: str,
    limit: int = Query(5, ge=1, le=20),
    user: User = Depends(require_scopes(["adr:read"]))
):
    """Find ADRs similar to a given one via semantic search."""
    adr = db_get(adr_id)
    if not adr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ADR '{adr_id}' not found")
    try:
        from app.services.embeddings import get_embedding_service
        from app.services.vector_store import get_vector_store, COLLECTION_ADRS
        text = f"{adr['title']}\n{adr.get('context', '')}\n{adr.get('decision', '')}"
        embedding = get_embedding_service().embed(text)
        vs = get_vector_store()
        if not vs:
            return {"adr_id": adr_id, "similar": []}
        results = vs.search(COLLECTION_ADRS, embedding, limit=limit + 1)
        results = [r for r in results if r["id"] != adr_id][:limit]
        return {"adr_id": adr_id, "similar": results}
    except Exception as e:
        return {"adr_id": adr_id, "similar": [], "error": str(e)}


@router.post("", response_model=ADR, status_code=status.HTTP_201_CREATED)
async def create_adr(
    adr_data: ADRCreate,
    user: User = Depends(require_scopes(["adr:write"]))
):
    """Create a new ADR."""
    adr = db_create(
        title=adr_data.title, context=adr_data.context,
        decision=adr_data.decision, consequences=adr_data.consequences,
        author=user.username, tags=adr_data.tags
    )
    _index_adr_in_vector_store(adr)
    return ADR(**_ensure_datetime(adr))


@router.put("/{adr_id}", response_model=ADR)
async def update_adr(
    adr_id: str,
    adr_data: ADRUpdate,
    user: User = Depends(require_scopes(["adr:write"]))
):
    """Update an existing ADR."""
    existing = db_get(adr_id)
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ADR '{adr_id}' not found")
    update_data = adr_data.model_dump(exclude_unset=True)
    update_data = {k: v for k, v in update_data.items() if v is not None}
    if not update_data:
        return ADR(**_ensure_datetime(existing))
    adr = db_update(adr_id, **update_data)
    _index_adr_in_vector_store(adr)
    return ADR(**_ensure_datetime(adr))


@router.patch("/{adr_id}/status", response_model=ADR)
async def update_adr_status(
    adr_id: str,
    new_status: ADRStatus,
    reason: Optional[str] = None,
    user: User = Depends(require_scopes(["adr:write"]))
):
    """Update ADR status."""
    existing = db_get(adr_id)
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ADR '{adr_id}' not found")
    adr = db_update(adr_id, status=new_status.value)
    return ADR(**_ensure_datetime(adr))


@router.delete("/{adr_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_adr(
    adr_id: str,
    user: User = Depends(require_scopes(["adr:delete"]))
):
    """Delete an ADR."""
    if not db_delete(adr_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ADR '{adr_id}' not found")
    try:
        from app.services.vector_store import get_vector_store, COLLECTION_ADRS
        vs = get_vector_store()
        if vs:
            vs.delete(COLLECTION_ADRS, adr_id)
    except Exception:
        pass
    return None


def _ensure_datetime(d: dict) -> dict:
    """Ensure datetime fields are datetime objects for Pydantic."""
    from datetime import datetime
    out = dict(d)
    for key in ("created_at", "updated_at"):
        v = out.get(key)
        if isinstance(v, str):
            try:
                out[key] = datetime.fromisoformat(v)
            except (ValueError, TypeError):
                out[key] = datetime.utcnow()
    return out
