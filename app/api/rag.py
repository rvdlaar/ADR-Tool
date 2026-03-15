"""RAG search + folder scan endpoints."""
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

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


# ---------------------------------------------------------------------------
# Folder scan + ingest
# ---------------------------------------------------------------------------

SCANNABLE_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".xml", ".csv"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB per file


class ScanRequest(BaseModel):
    path: str


class IngestFilesRequest(BaseModel):
    path: str
    files: List[str]  # relative file paths within the folder


@router.post("/scan")
async def scan_folder(
    req: ScanRequest,
    user=Depends(require_scopes(["adr:write"]))
):
    """Scan a folder and return list of ingestible files."""
    folder = Path(os.path.expanduser(req.path)).resolve()

    if not folder.exists():
        return {"error": f"Folder not found: {req.path}", "files": []}
    if not folder.is_dir():
        return {"error": f"Not a directory: {req.path}", "files": []}

    files = []
    by_ext = {}
    total_size = 0

    for f in sorted(folder.rglob("*")):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext not in SCANNABLE_EXTENSIONS:
            continue
        if f.stat().st_size > MAX_FILE_SIZE:
            continue
        # Skip hidden files and common non-doc directories
        parts = f.relative_to(folder).parts
        if any(p.startswith('.') or p in ('node_modules', '__pycache__', 'dist', 'build', '.git') for p in parts):
            continue

        rel = str(f.relative_to(folder))
        size = f.stat().st_size
        files.append({"path": rel, "name": f.name, "ext": ext, "size": size})
        by_ext[ext] = by_ext.get(ext, 0) + 1
        total_size += size

    return {
        "folder": str(folder),
        "files": files,
        "total": len(files),
        "by_extension": by_ext,
        "total_size_kb": round(total_size / 1024, 1),
    }


@router.post("/ingest-files")
async def ingest_files(
    req: IngestFilesRequest,
    user=Depends(require_scopes(["adr:write"]))
):
    """Ingest files with SSE progress streaming."""
    import asyncio
    import json as json_mod
    from fastapi.responses import StreamingResponse
    from app.db.document_store import create_document
    from app.services.embeddings import get_embedding_service
    from app.services.vector_store import get_vector_store, COLLECTION_CONTEXT

    folder = Path(os.path.expanduser(req.path)).resolve()
    if not folder.is_dir():
        return {"error": "Invalid folder", "ingested": 0}

    async def stream():
        ingested = 0
        total = len(req.files)

        for i, rel_path in enumerate(req.files):
            file_path = (folder / rel_path).resolve()
            status = "processing"
            error = None

            try:
                file_path.relative_to(folder)
            except ValueError:
                status = "error"
                error = "Path traversal blocked"
                yield f"data: {json_mod.dumps({'file': rel_path, 'index': i, 'total': total, 'status': status, 'error': error})}\n\n"
                continue

            # Send "processing" event
            yield f"data: {json_mod.dumps({'file': rel_path, 'index': i, 'total': total, 'status': 'reading'})}\n\n"

            if not file_path.exists() or not file_path.is_file():
                yield f"data: {json_mod.dumps({'file': rel_path, 'index': i, 'total': total, 'status': 'error', 'error': 'Not found'})}\n\n"
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                if not content.strip():
                    yield f"data: {json_mod.dumps({'file': rel_path, 'index': i, 'total': total, 'status': 'skipped', 'error': 'Empty file'})}\n\n"
                    continue

                # Store in SQLite
                doc = create_document(
                    doc_id=None, filename=file_path.name,
                    original_filename=rel_path, file_path=str(file_path),
                    file_size=len(content.encode()), content_type="text/plain",
                    source="folder_scan",
                )

                yield f"data: {json_mod.dumps({'file': rel_path, 'index': i, 'total': total, 'status': 'embedding'})}\n\n"

                # Embed and index
                try:
                    vs = get_vector_store()
                    if vs:
                        emb = get_embedding_service()
                        text = f"{file_path.name}\n{content[:5000]}"
                        embedding = emb.embed(text)
                        vs.upsert(COLLECTION_CONTEXT, doc["id"], embedding, text, {
                            "filename": file_path.name,
                            "source": "folder_scan",
                            "path": rel_path,
                        })
                except Exception:
                    pass

                ingested += 1
                yield f"data: {json_mod.dumps({'file': rel_path, 'index': i, 'total': total, 'status': 'done'})}\n\n"

            except Exception as e:
                yield f"data: {json_mod.dumps({'file': rel_path, 'index': i, 'total': total, 'status': 'error', 'error': str(e)})}\n\n"

            await asyncio.sleep(0)  # yield control

        yield f"data: {json_mod.dumps({'status': 'complete', 'ingested': ingested, 'total': total})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
