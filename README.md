# ADR Tool API

A secure REST API for managing Architecture Decision Records (ADRs) with AI-powered generation capabilities.

## Features

- **Dual Authentication**: OAuth2/JWT tokens and API Keys
- **Strict CORS**: Only explicitly allowed origins
- **Role-Based Access Control**: Scopes for granular permissions
- **Security Headers**: CSP, X-Frame-Options, etc.
- **FastAPI**: Modern, fast Python web framework
- **Interactive Documentation**: Swagger UI and ReDoc
- **AI-Powered ADR Generation**: Generate Architecture Decision Records using LLM

## Quick Start

### 1. Using Docker (Recommended)

```bash
# Clone and setup
git clone https://github.com/rvdlaar/ADR-Tool.git
cd ADR-Tool/adr-tool-api

# Configure environment
cp .env.example .env
# Edit .env with your settings (especially AI_API_KEY)

# Run with Docker Compose
docker-compose up -d
```

### 2. Manual Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run the server
uvicorn app.main:app --reload
```

### 3. Access Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## AI Configuration

To enable AI-powered ADR generation, set these environment variables:

```bash
# Required: Your API key
AI_API_KEY=sk-your-api-key-here

# Optional: Provider (openai, openrouter, etc.)
AI_PROVIDER=openai

# Optional: Model to use
AI_MODEL=gpt-4o-mini

# Optional: For self-hosted or alternative providers
AI_BASE_URL=https://api.openai.com/v1
```

### Supported AI Providers

- **OpenAI** - Use `AI_PROVIDER=openai` with your OpenAI API key
- **OpenRouter** - Use `AI_PROVIDER=openrouter` with your OpenRouter API key
- **Ollama** - Use `AI_BASE_URL=http://localhost:11434/v1` for local models
- **Anthropic** - Use with compatible API (via base_url)

## API Examples

### Login and Get Token

```bash
curl -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin&scope=adr:read+adr:write"
```

### Generate an ADR with AI

```bash
curl -X POST "http://localhost:8000/api/v1/adrs/generate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Use PostgreSQL for Primary Database",
    "description": "We need a reliable, ACID-compliant database for our core data",
    "requirements": [
      "ACID compliance",
      "High availability",
      "JSON support"
    ],
    "constraints": [
      "Must be open source",
      "Must support Linux"
    ]
  }'
```

### Generate a Draft (Preview)

```bash
curl -X POST "http://localhost:8000/api/v1/adrs/generate/draft" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Use Redis for Caching",
    "description": "Improve application performance with caching"
  }'
```

### Create an ADR Manually

```bash
curl -X POST "http://localhost:8000/api/v1/adrs" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Use OAuth2 for Authentication",
    "context": "We need secure authentication",
    "decision": "Implement OAuth2 with JWT",
    "consequences": "More secure but more complex"
  }'
```

### List ADRs

```bash
curl -X GET "http://localhost:8000/api/v1/adrs" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Project Structure

```
adr-tool-api/
├── app/
│   ├── api/
│   │   ├── auth.py         # Authentication endpoints
│   │   ├── adrs.py         # ADR CRUD endpoints
│   │   └── ai_generate.py  # AI ADR generation endpoints
│   ├── core/
│   │   ├── config.py       # Configuration
│   │   ├── cors.py         # CORS configuration
│   │   └── security.py     # Authentication & security
│   ├── models/
│   │   └── adr.py          # ADR data models
│   ├── schemas/
│   │   └── adr.py          # Pydantic schemas
│   ├── services/
│   │   └── ai_generator.py # AI generation service
│   └── main.py             # Application entry point
├── tests/
│   └── test_security.py    # Security tests
├── docker-compose.yml      # Docker Compose configuration
├── Dockerfile              # Docker image definition
├── .env.example            # Example configuration
├── SECURITY.md             # Security implementation details
├── SECURITY_REMEDIATION.md # Security fixes from audit
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Security

See [SECURITY.md](SECURITY.md) for detailed security implementation documentation.

## Demo Credentials

The following test users are available (password: "password123"):

- **admin**: Full access (adr:read, adr:write, adr:delete, admin:users, admin:settings)
- **user**: Read/write access (adr:read, adr:write)
- **reader**: Read-only access (adr:read)

## License

MIT
