# ADR Tool

AI-powered Architecture Decision Record generator with RAG, quality validation, conflict detection, and export to any folder. Download, double-click, start making decisions — AI runs locally, no setup required.

## What It Does

Give it a title and context, and it generates a comprehensive ADR with:
- **Y-Statement** summary (one sentence capturing the entire decision)
- **Alternatives comparison table** (not just pros/cons — why each was rejected)
- **Impact table** (which roles are affected, how, what they need to do)
- **Reversibility analysis** (can you undo this? at what cost?)
- **Quality validation** (score 1-10, auto-retries if below threshold, section-level highlighting)
- **Conflict detection** (warns if the decision contradicts existing ADRs)
- **RAG provenance** (shows which documents informed the generation)

Feed it your existing docs (point to a folder) and it becomes context-aware — new ADRs are consistent with prior decisions.

## Quick Start

### Option A: Download & Run (Recommended)

No Docker, no terminal, no API keys needed.

1. **Download** the latest release from [Releases](https://github.com/rvdlaar/ADR-Tool/releases)
2. **Unzip** to any folder
3. **Double-click** `ADR-Tool.exe` (Windows) or `ADR-Tool` (macOS)
4. **Browser opens** — start creating architecture decisions

Everything runs locally. A bundled language model handles generation, validation, and conflict detection — no cloud services, no API keys, no data leaving your device.

> **Power users:** Want to use your own OpenRouter key, Azure OpenAI, or local Ollama? Open **Settings** and override the AI endpoint.

### Option B: Docker Compose (Power Users)

Full control over models and providers.

```bash
git clone https://github.com/rvdlaar/ADR-Tool.git
cd ADR-Tool
docker compose up -d
# Open http://localhost:8000
```

Two services start: the ADR API (port 8000) and ChromaDB for vector search (port 8002).

Configure your own AI provider in **Settings**, or set `AI_API_KEY` and `AI_BASE_URL` in the environment.

### Option C: IT Deployment (Intune/MDM)

Same bundle as Option A, wrapped in MSIX/MSI for managed devices. IT admins can pre-configure by placing a `config.json` in the `data/` folder (e.g., pointing AI at a corporate Azure OpenAI endpoint). Users open the app — no setup required.

## Using the Frontend

1. **First launch** → onboarding wizard: enter API key, model, output folder
2. **New** → enter title + description → **Generate ADR**
3. **Review** → edit any section inline → validation score shows quality
4. **Accept** → ADR saved + auto-exported to your output folder as `.md`
5. **Export** → Copy as Markdown or Download `.md` from any ADR
6. **Knowledge** → scan a folder, ingest docs for RAG context, or import existing ADRs
7. **Settings** → change API key, model, output folder without restart

Keyboard: `Cmd+N` (new), `Cmd+K` (search), `Esc` (back)

## Key Features

### Generation
- Hybrid ADR format: Nygard + Y-statement + Impact table
- Two profiles: `detailed` (metric-driven) and `guided` (with explanations)
- RAG-augmented: retrieves related ADRs + context docs before generating
- Auto-retry if quality score < 7

### Quality
- Layer 1: free heuristic checks (structure, vague terms, constraints)
- Layer 2: LLM scoring (only when Layer 1 flags issues — cost-rightized)
- Section-level highlights: weak sections marked with amber indicator
- Staleness detection: ADRs > 90 days flagged for review

### Export & Import
- **Copy as Markdown** — one click to clipboard
- **Download .md** — numbered file (adr-001-title.md)
- **Bulk export** — all ADRs as one download
- **Auto-save** — accepted ADRs written to configurable output folder (local, network drive, OneDrive, SharePoint)
- **Import** — parse existing ADR `.md` files into the registry + RAG index

### Decision Registry
- Supersession chains: mark which ADR replaces which
- Cross-linking: ADR references (ADR-1, ADR-3) become clickable links
- Conflict detection: heuristic + LLM check against existing decisions
- Semantic search with section matching ("matched in Decision" vs "matched in Alternatives")

### Knowledge Base
- Scan any folder for `.md`, `.txt`, `.json`, `.yaml` files
- Select all or pick specific files
- Real-time SSE progress during ingestion
- Documents indexed in ChromaDB for RAG context

### Settings (no `.env` required)
- API key, model, base URL — configurable from UI
- Output folder — local path, network drive, or synced folder
- Settings persist in `data/settings.json`, applied on startup

## ADR Format

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
| `PATCH` | `/api/v1/adrs/{id}/status` | Change status |
| `DELETE` | `/api/v1/adrs/{id}` | Delete ADR |
| `GET` | `/api/v1/adrs/{id}/similar` | Find similar ADRs (semantic) |

### AI Generation

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/adrs/generate` | Generate + save with RAG + validation + conflicts |
| `POST` | `/api/v1/adrs/generate/draft` | Generate draft (no save) |

Response includes: `adr`, `validation` (score, issues, suggestions), `conflicts`, `related_adrs` (provenance), `review_required`.

### RAG / Knowledge Base

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/rag/search?q=...` | Semantic search |
| `GET` | `/api/v1/rag/stats` | Index statistics |
| `POST` | `/api/v1/rag/scan` | Scan folder for files |
| `POST` | `/api/v1/rag/ingest-files` | Ingest files (SSE progress) |
| `POST` | `/api/v1/rag/import-adrs` | Import .md files as ADRs |

### Settings

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/settings` | Get settings (key masked) |
| `PUT` | `/api/v1/settings` | Update settings |
| `POST` | `/api/v1/settings/save-adr-to-folder` | Save .md to output folder |

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
│   ├── adrs table (all 10 sections persisted)
│   ├── documents table (ingested doc metadata)
│   ├── users table (auth)
│   └── settings.json (API key, output folder)
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
→ Score < 7? → Retry once with feedback → Conflict detection → Architect reviews
```

Cost per ADR: ~$0.01 happy path, ~$0.024 worst case.

## Project Structure

```
├── app/
│   ├── api/
│   │   ├── auth.py              # OAuth2/JWT authentication
│   │   ├── adrs.py              # ADR CRUD + similar + cross-linking
│   │   ├── ai_generate.py       # Generation + validation + conflicts + provenance
│   │   ├── ingest.py            # File upload endpoints
│   │   ├── rag.py               # Search, scan, ingest (SSE), import ADRs
│   │   └── settings.py          # API key, model, output folder
│   ├── core/                    # Security, config, CORS
│   ├── db/                      # SQLite persistence (ADRs + documents)
│   ├── services/                # AI generator, validator, conflict detector, embeddings, vector store
│   └── main.py                  # FastAPI app
├── static/index.html            # Frontend SPA
├── docker-compose.yml           # API + ChromaDB
├── Dockerfile                   # Python 3.11
└── data/                        # Persistent (volume-mounted)
    ├── adrs.db                  # SQLite database
    ├── users.db                 # User auth database
    └── settings.json            # UI-configured settings
```

## Security

- OAuth2/JWT with scoped access (adr:read, adr:write, adr:delete, admin:*)
- API key authentication for server-to-server
- Strict CORS, security headers (CSP, X-Frame-Options)
- Rate limiting (configurable per minute)
- Path traversal protection on all file operations
- API key masked in settings GET response

See [SECURITY.md](SECURITY.md) for details.

## License

MIT
