# ADR Tool

AI-powered Architecture Decision Record generator with RAG, quality validation, and conflict detection.

## What It Does

Give it a title and context, and it generates a comprehensive ADR with:
- **Y-Statement** summary (one sentence capturing the entire decision)
- **Alternatives comparison table** (not just pros/cons — why each was rejected)
- **Impact table** (which roles are affected, how, what they need to do)
- **Reversibility analysis** (can you undo this? at what cost?)
- **Quality validation** (score 1-10, auto-retries if below threshold)
- **Conflict detection** (warns if the decision contradicts existing ADRs)

Feed it your existing docs (point to a folder) and it becomes context-aware — new ADRs are consistent with prior decisions.

## Quick Start

```bash
git clone https://github.com/rvdlaar/ADR-Tool.git
cd ADR-Tool

cp .env.example .env
# Set AI_API_KEY in .env

docker compose up -d
# Open http://localhost:8000
```

Two services start: the ADR API (port 8000) and ChromaDB for vector search (port 8002).

## Using the Frontend

1. Open `http://localhost:8000` — the web UI loads
2. Click **New** — enter a title and description
3. Optionally: paste a folder path → **Scan** → **Ingest all** (indexes your docs for RAG)
4. Optionally: expand constraints, alternatives, impact sections
5. Click **Generate ADR**
6. Review the result — edit any section inline
7. Click **Accept this ADR** or **Regenerate**

Keyboard shortcuts: `Cmd+N` (new), `Cmd+K` (search), `Esc` (back)

## ADR Format

Hybrid format combining Nygard, Y-statements, and Impact analysis:

| Section | Purpose |
|---------|---------|
| Y-Statement | One-sentence decision summary |
| Context | Situation, forces, assumptions |
| Decision Drivers | Why this decision is happening now |
| Decision | The specific change and rationale |
| Alternatives | Comparison table with rejection reasons |
| Consequences | Positive, negative, and risks — with metrics |
| Impact | Per-role: who, what changes, action needed |
| Reversibility | Can it be undone? Point of no return? Rollback plan? |
| Related Decisions | Links to ADRs this supersedes or depends on |

## API Endpoints

### ADR Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/adrs` | List ADRs (paginated, filterable) |
| `GET` | `/api/v1/adrs/{id}` | Get single ADR |
| `POST` | `/api/v1/adrs` | Create ADR manually |
| `PUT` | `/api/v1/adrs/{id}` | Update ADR |
| `DELETE` | `/api/v1/adrs/{id}` | Delete ADR |
| `GET` | `/api/v1/adrs/{id}/similar` | Find similar ADRs (semantic) |

### AI Generation

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/adrs/generate` | Generate + save ADR with RAG + validation |
| `POST` | `/api/v1/adrs/generate/draft` | Generate draft (no save) |

Generation request accepts: `title`, `description`, `context`, `requirements`, `constraints`, `alternatives`, `decision_drivers`, `impacted_roles`, `success_criteria`, `timeline`, `scope`, `profile` ("detailed" or "guided").

Response includes: `adr`, `validation` (score, issues, suggestions), `conflicts` (detected contradictions), `review_required`.

### RAG / Knowledge Base

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/rag/search?q=...` | Semantic search across ADRs + docs |
| `GET` | `/api/v1/rag/stats` | Index statistics |
| `POST` | `/api/v1/rag/scan` | Scan a folder for ingestible files |
| `POST` | `/api/v1/rag/ingest-files` | Ingest selected files (SSE progress) |

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/token` | Login (OAuth2) |
| `POST` | `/api/v1/auth/refresh` | Refresh token |
| `GET` | `/api/v1/auth/me` | Current user |

## Architecture

```
ADR Tool
├── FastAPI (API + static frontend)
├── SQLite (persistent storage, WAL mode)
│   ├── adrs table (all sections persisted)
│   ├── documents table (ingested doc metadata)
│   └── users table (auth)
├── ChromaDB (vector store)
│   ├── adrs collection (embedded ADR text)
│   └── context_docs collection (embedded ingested docs)
└── OpenAI-compatible LLM
    ├── Generation (gpt-4o-mini default)
    ├── Embeddings (text-embedding-3-small)
    └── Validation scoring (same model, cheap calls)
```

### Quality Pipeline

```
Generate → Layer 1 (free heuristics) → Issues? → Layer 2 (LLM scoring)
→ Score < 7? → Retry once with feedback → Return with score + suggestions
→ Conflict detection (heuristic + optional LLM) → Architect reviews
```

Cost per ADR: ~$0.01 happy path, ~$0.024 worst case (retry + conflict check).

## Configuration

```bash
# Required
AI_API_KEY=sk-...              # OpenAI, OpenRouter, or compatible

# Optional
AI_PROVIDER=openai             # openai, openrouter, ollama
AI_MODEL=gpt-4o-mini           # Generation model
AI_BASE_URL=                   # For alternative providers
EMBEDDING_MODEL=text-embedding-3-small
CHROMA_URL=http://chromadb:8000
SECRET_KEY=change-me           # JWT signing key
ENVIRONMENT=development        # development or production
RATE_LIMIT_PER_MINUTE=60
```

## Project Structure

```
├── app/
│   ├── api/
│   │   ├── auth.py              # OAuth2/JWT authentication
│   │   ├── adrs.py              # ADR CRUD + similar search
│   │   ├── ai_generate.py       # Generation with validation + conflicts
│   │   ├── ingest.py            # File upload endpoints
│   │   └── rag.py               # Search, scan, folder ingest (SSE)
│   ├── core/
│   │   ├── config.py            # Settings
│   │   ├── cors.py              # CORS + security headers
│   │   ├── security.py          # JWT, API keys, RBAC
│   │   └── user_store.py        # SQLite user persistence
│   ├── db/
│   │   ├── adr_store.py         # ADR SQLite CRUD
│   │   └── document_store.py    # Document metadata SQLite
│   ├── models/
│   │   └── adr.py               # Pydantic models
│   ├── schemas/
│   │   └── adr.py               # Request/response schemas
│   ├── services/
│   │   ├── ai_generator.py      # LLM generation + RAG context
│   │   ├── adr_validator.py     # Quality validation (heuristic + LLM)
│   │   ├── conflict_detector.py # Conflict detection (heuristic + LLM)
│   │   ├── embeddings.py        # Embedding service
│   │   ├── ingest.py            # File ingestion service
│   │   └── vector_store.py      # ChromaDB wrapper
│   └── main.py                  # FastAPI app + static files
├── static/
│   └── index.html               # Frontend SPA
├── docker-compose.yml           # API + ChromaDB
├── Dockerfile                   # Python 3.11 image
└── requirements.txt             # Dependencies
```

## Security

- OAuth2/JWT with scoped access (adr:read, adr:write, adr:delete, admin:*)
- API key authentication for server-to-server
- Strict CORS, security headers (CSP, HSTS, X-Frame-Options)
- Rate limiting (configurable per minute)
- Path traversal protection on file ingestion
- Folder scan restricted to safe extensions, skips hidden dirs

See [SECURITY.md](SECURITY.md) for details.

## License

MIT
