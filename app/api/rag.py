"""RAG search endpoints."""
from fastapi import APIRouter, Depends, Query
from app.core.security import require_scopes

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=2),
    limit: int = Query(5, ge=1, le=20),
    collection: str = Query("all"),
    user=Depends(require_scopes(["adr:read"]))
):
    """Semantic search across ADRs and context documents."""
    from app.services.embeddings import get_embedding_service, EmbeddingError
    from app.services.vector_store import get_vector_store, COLLECTION_ADRS, COLLECTION_CONTEXT

    try:
        emb_service = get_embedding_service()
        vector_store = get_vector_store()
        if not vector_store:
            return {"error": "Vector store unavailable", "results": []}
        query_embedding = emb_service.embed(q)
    except EmbeddingError as e:
        return {"error": str(e), "results": []}
    except Exception as e:
        return {"error": f"Search unavailable: {e}", "results": []}

    results = []
    collections = []
    if collection in ("all", "adrs"):
        collections.append(COLLECTION_ADRS)
    if collection in ("all", "context_docs"):
        collections.append(COLLECTION_CONTEXT)

    for coll_name in collections:
        try:
            hits = vector_store.search(coll_name, query_embedding, limit=limit)
            for h in hits:
                h["collection"] = coll_name
            results.extend(hits)
        except Exception:
            continue

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"results": results[:limit], "query": q, "count": len(results[:limit])}


@router.get("/stats")
async def rag_stats(user=Depends(require_scopes(["adr:read"]))):
    """RAG index statistics."""
    from app.services.vector_store import get_vector_store, COLLECTION_ADRS, COLLECTION_CONTEXT
    vs = get_vector_store()
    if not vs:
        return {"error": "Vector store unavailable", "adrs_indexed": 0, "context_docs_indexed": 0}
    return {
        "adrs_indexed": vs.count(COLLECTION_ADRS),
        "context_docs_indexed": vs.count(COLLECTION_CONTEXT),
    }
