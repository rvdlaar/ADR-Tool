# ADR-Tool — RAG Pipeline Specification

## Overview

The ADR-Tool currently generates Architecture Decision Records using LLM prompts, but the
AI has no awareness of previously generated ADRs or ingested reference documents. Adding a
RAG pipeline connects the existing ingestion layer (which already stores files securely) to
the generation layer, so that every new ADR is automatically grounded in prior decisions and
uploaded context documents. The result: generated ADRs are consistent with the existing
decision record, avoid re-litigating settled choices, and inherit the project's established
patterns.

---

## Architecture

```
INGESTION                    VECTOR STORE                GENERATION
---------                    ------------                ----------
POST /api/v1/ingest/upload   ChromaDB                    POST /api/v1/ai/generate
       |                         |                               |
       v                         |                               v
ingest_service.py  --embed-->  collection: context_docs    ai_generator.py
                                                                 |
POST /api/v1/adrs  --embed-->  collection: adrs             1. retrieve top-k
                                                             2. build augmented prompt
GET /api/v1/rag/search                                       3. call LLM
GET /api/v1/adrs/{id}/similar                                4. return GeneratedADR
       |                         |
       v                         |
 EmbeddingService  ---------->  VectorStore
 (OpenAI text-embedding-3-small, same client as generation)
```

---

## Components

### EmbeddingService (`app/services/embeddings.py`)

**Purpose:** Generate embeddings for any text using the same OpenAI-compatible client that
`ADRGenerator` already uses. Reuses `AI_API_KEY`, `AI_BASE_URL`, same provider.

**Interface:**
```python
class EmbeddingService:
    def __init__(self):
        # reads AI_API_KEY, AI_BASE_URL from env
        # model: EMBEDDING_MODEL env var, default "text-embedding-3-small"

    def embed(self, text: str) -> list[float]:
        """Embed a single string. Returns 1536-dim vector."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of strings in one API call (max 100 per call)."""
```

**Dependencies:** `openai>=1.12.0` (already in requirements.txt)

**Notes:**
- Strip and truncate text to 8000 tokens before embedding to stay within model limits.
- Raise `EmbeddingError(Exception)` on API failure — callers must handle gracefully so that
  ingestion still succeeds even if ChromaDB is unavailable.

---

### VectorStore (`app/services/vector_store.py`)

**Purpose:** Thin wrapper around the ChromaDB HTTP client. Manages two named collections.

**Interface:**
```python
COLLECTION_ADRS = "adrs"
COLLECTION_CONTEXT = "context_docs"

class VectorStore:
    def __init__(self):
        # reads CHROMA_URL env var, default "http://chromadb:8000"

    def upsert(
        self,
        collection: str,
        doc_id: str,
        embedding: list[float],
        text: str,
        metadata: dict,
    ) -> None:
        """Add or update a document in the given collection."""

    def search(
        self,
        collection: str,
        embedding: list[float],
        limit: int = 5,
    ) -> list[dict]:
        """
        Returns list of:
        {
            "id": str,
            "text": str,
            "metadata": dict,
            "score": float,   # cosine distance, lower = more similar
        }
        sorted ascending by score.
        """

    def search_all(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[dict]:
        """Search across both collections, merge, re-rank by score, return top limit."""

    def delete(self, collection: str, doc_id: str) -> None:
        """Remove a document from a collection."""
```

**Dependencies:** `chromadb-client>=0.4.0` (HTTP client only, not the embedded server)

**Error handling:** If ChromaDB is unreachable, raise `VectorStoreUnavailableError`. Callers
in ingestion must catch this and log a warning — the document is still saved to disk,
embedding is deferred.

---

### RAG Router (`app/api/rag.py`)

**Purpose:** Exposes semantic search endpoints.

**Interface:**
```python
router = APIRouter(prefix="/rag", tags=["RAG"])
```

Two endpoints — see API Endpoints section below.

**Dependencies:** `EmbeddingService`, `VectorStore`, `require_scopes(["adr:read"])`

---

### Modified: ADRGenerator (`app/services/ai_generator.py`)

**Purpose:** Before calling the LLM, retrieve related ADRs and context documents, then inject
them into the generation prompt.

**Changes:**
- Add `__init__` dependency on `EmbeddingService` and `VectorStore` (lazy singletons).
- Add private method `_retrieve_context(request: ADRGenerationRequest) -> str`.
- Modify `_build_prompt` to accept optional `retrieved_context: str` parameter.
- In `generate()`, call `_retrieve_context` before `_build_prompt`.

**`_retrieve_context` logic:**
```
query_text = f"{request.title} {request.description} {request.context or ''}"
embedding  = embedding_service.embed(query_text)
results    = vector_store.search_all(embedding, limit=5)
format each result as:
  "### [metadata.title or metadata.filename]\n{text}\n"
join with "\n---\n"
```

If `EmbeddingService` or `VectorStore` raises, log the error and return `""` — generation
must never fail because RAG is unavailable.

**Prompt injection:** Insert retrieved context between the existing "Input Information" block
and the "Output Format" block:

```
## Related Decisions and Context

{retrieved_context}

---
```

---

### Modified: ingest service (`app/services/ingest.py`)

**Purpose:** After a file is successfully written to disk, extract its text content, generate
an embedding, and upsert into the `context_docs` ChromaDB collection.

**Changes to `ingest_file_api`:**
```python
# Existing: write file, compute hash, store in _documents_db
# Add after _documents_db[doc_id] = document:

try:
    text = _extract_text(file_content, filename)
    embedding = get_embedding_service().embed(text)
    get_vector_store().upsert(
        collection=COLLECTION_CONTEXT,
        doc_id=doc_id,
        embedding=embedding,
        text=text[:4000],        # truncate stored text to keep ChromaDB lean
        metadata={
            "filename": filename,
            "doc_id": doc_id,
            "ingested_at": document["ingested_at"],
        },
    )
except Exception as e:
    logger.warning(f"RAG embedding skipped for {doc_id}: {e}")
```

Add `_extract_text(content: bytes, filename: str) -> str`:
- `.txt`, `.md`, `.csv`, `.json`, `.yaml`, `.yml`, `.xml` — decode as UTF-8.
- `.pdf` — use `pypdf` (add to requirements); extract page text, join with newline.
- `.doc`, `.docx` — skip for now; store filename as placeholder text.
- Default fallback: decode UTF-8 with errors='replace'.

Apply the same pattern in `ingest_file_path`.

**Also:** When a new ADR is saved via `POST /api/v1/adrs`, embed it and upsert into the
`adrs` collection. Wire this in `app/api/adrs.py` in the `create_adr` handler after the
record is stored in `_adrs_db`.

```python
# After _adrs_db[adr_id] = adr:
try:
    text = f"{adr.title}\n{adr.context}\n{adr.decision}\n{adr.consequences}"
    embedding = get_embedding_service().embed(text)
    get_vector_store().upsert(
        collection=COLLECTION_ADRS,
        doc_id=adr_id,
        embedding=embedding,
        text=text[:4000],
        metadata={"title": adr.title, "status": adr.status, "adr_id": adr_id},
    )
except Exception as e:
    logger.warning(f"RAG embedding skipped for ADR {adr_id}: {e}")
```

---

## API Endpoints

### `GET /api/v1/rag/search`

Semantic search across both ChromaDB collections.

**Auth:** `adr:read` scope

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | required | Search query text |
| `limit` | int | 5 | Max results (1–20) |
| `collection` | string | `"all"` | `"adrs"`, `"context_docs"`, or `"all"` |

**Response `200`:**
```json
{
  "query": "event sourcing vs CQRS",
  "results": [
    {
      "id": "abc123",
      "collection": "adrs",
      "text": "...",
      "score": 0.12,
      "metadata": {
        "title": "3. Use Event Sourcing for Order Service",
        "status": "Accepted",
        "adr_id": "abc123"
      }
    }
  ]
}
```

**Response `400`:** `{ "detail": "query 'q' is required" }`
**Response `503`:** `{ "detail": "Vector store unavailable" }` — when ChromaDB is down.

---

### `GET /api/v1/adrs/{adr_id}/similar`

Find ADRs similar to a given ADR by fetching its stored embedding.

**Auth:** `adr:read` scope

**Path param:** `adr_id` — existing ADR ID

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 5 | Max results (1–10) |

**Response `200`:**
```json
{
  "adr_id": "abc123",
  "similar": [
    {
      "id": "def456",
      "collection": "adrs",
      "text": "...",
      "score": 0.08,
      "metadata": { "title": "5. CQRS for Read Models", "status": "Proposed" }
    }
  ]
}
```

**Response `404`:** ADR not found in ChromaDB (was created before RAG was enabled).
**Response `503`:** ChromaDB unavailable.

**Implementation note:** Fetch the ADR's embedding by calling
`vector_store.get_embedding(COLLECTION_ADRS, adr_id)` — ChromaDB `collection.get()` with
`include=["embeddings"]`. Then call `vector_store.search(COLLECTION_ADRS, embedding, limit+1)`
and exclude the ADR itself from results.

---

## Data Flow

### Ingestion flow

1. Client calls `POST /api/v1/ingest/upload` with a file.
2. `ingest_service.ingest_file_api()` validates, sanitizes, writes to disk.
3. `_extract_text()` converts bytes to plain text.
4. `EmbeddingService.embed(text)` calls `text-embedding-3-small` via OpenAI-compatible API.
5. `VectorStore.upsert(collection="context_docs", ...)` stores in ChromaDB.
6. On any step 4–5 failure: log warning, return the ingestion response anyway (doc is on disk).
7. API returns `IngestResponse` with `doc_id`.

### Generation flow (RAG-augmented)

1. Client calls `POST /api/v1/ai/generate` with `ADRGenerationRequest`.
2. `ADRGenerator.generate()` calls `_retrieve_context(request)`.
3. `_retrieve_context` embeds `title + description + context`.
4. `VectorStore.search_all(embedding, limit=5)` queries both collections.
5. Top results are formatted as a "Related Decisions and Context" block.
6. `_build_prompt(request, retrieved_context=...)` produces the augmented prompt.
7. LLM call proceeds as before; returns `GeneratedADR`.
8. On steps 3–5 failure: `_retrieve_context` returns `""`, generation continues unaugmented.

### ADR creation flow

1. Client calls `POST /api/v1/adrs` with `ADRCreate`.
2. ADR is saved to `_adrs_db` as before.
3. ADR text is embedded and upserted into the `adrs` ChromaDB collection.
4. On embedding failure: log warning, return the created ADR normally.

---

## Configuration

New environment variables (add to `.env.example` and `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `CHROMA_URL` | `http://chromadb:8000` | ChromaDB HTTP endpoint |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name |
| `RAG_RETRIEVE_LIMIT` | `5` | How many results to inject into generation prompt |
| `RAG_ENABLED` | `true` | Set to `false` to disable RAG (generation still works) |

Existing variables reused for embeddings: `AI_API_KEY`, `AI_BASE_URL`.

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `app/services/embeddings.py` | Create | `EmbeddingService` class + `get_embedding_service()` singleton |
| `app/services/vector_store.py` | Create | `VectorStore` class + `get_vector_store()` singleton |
| `app/api/rag.py` | Create | `/rag/search` and `/adrs/{id}/similar` endpoints |
| `app/services/ingest.py` | Modify | Add `_extract_text()`, embed + upsert after file write |
| `app/services/ai_generator.py` | Modify | Add `_retrieve_context()`, augment prompt |
| `app/api/adrs.py` | Modify | Embed + upsert ADR after create |
| `app/main.py` | Modify | Register `rag.router` at `/api/v1` |
| `requirements.txt` | Modify | Add `chromadb-client>=0.4.0`, `pypdf>=4.0.0` |
| `docker-compose.yml` | Modify | Add ChromaDB service, add `CHROMA_URL` env var |
| `.env.example` | Modify | Document new env vars |

---

## ChromaDB docker-compose Addition

Add this service to `docker-compose.yml`:

```yaml
  chromadb:
    image: chromadb/chroma:latest
    container_name: adr-chromadb
    ports:
      - "8002:8000"   # 8002 to avoid conflict if PSA-Tool is also running
    volumes:
      - chroma_data:/chroma/chroma
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  chroma_data:
```

Add to the `adr-tool-api` service environment:
```yaml
      - CHROMA_URL=${CHROMA_URL:-http://chromadb:8000}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-small}
      - RAG_RETRIEVE_LIMIT=${RAG_RETRIEVE_LIMIT:-5}
      - RAG_ENABLED=${RAG_ENABLED:-true}
```

Add `depends_on: [chromadb]` to the `adr-tool-api` service (soft dependency — app must
tolerate ChromaDB being absent via the `VectorStoreUnavailableError` guard).

---

## Acceptance Criteria

- [ ] `POST /api/v1/ingest/upload` with a `.md` file returns `200` and a record appears in
      ChromaDB `context_docs` collection (verify via `GET /api/v1/rag/search?q=<keyword>`).
- [ ] `POST /api/v1/ai/generate` for a topic that matches an existing ADR returns a
      `GeneratedADR` whose prompt log (or debug header) shows retrieved context was injected.
- [ ] `GET /api/v1/rag/search?q=event+sourcing&limit=3` returns up to 3 results with `score`
      field and correct `collection` attribution.
- [ ] `GET /api/v1/adrs/{id}/similar` returns semantically related ADRs, excluding the ADR
      itself from results.
- [ ] When ChromaDB is stopped, `POST /api/v1/ai/generate` still returns a generated ADR
      (degraded but functional); ingestion still stores the file.
- [ ] When `RAG_ENABLED=false`, generation prompt contains no retrieval block.
- [ ] `pypdf` extracts text from a test PDF; result appears in search.
- [ ] All new endpoints are protected by `adr:read` scope.

---

## Out of Scope

- Persistent ADR database (in-memory storage is not changed by this spec).
- Chunking strategy for large documents (embed full text up to token limit, defer chunking).
- Re-indexing existing ADRs on startup (deferred — only new ADRs are indexed going forward).
- User-facing UI for RAG search (API only).
- Hybrid search (BM25 + vector) — pure vector search is sufficient for this phase.
- Multi-tenancy / per-user collections.
- Streaming generation responses.
