# Codebase Knowledge Intelligence Platform

An AI-powered knowledge graph that mines git history, PRs, code comments, and architectural decision records to build a queryable, living intelligence layer over any codebase.

## Prerequisites

- Docker & Docker Compose (v2+)
- Python 3.11+
- Node.js 18+
- OpenAI API key (or Ollama running locally as fallback)
- Git

## Quick Start

### 1. Clone and Configure

```bash
git clone <repo>
cd codebase-knowledge-platform
cp .env.example .env
# Edit .env and fill in your API keys
```

### 2. Start Infrastructure Services

```bash
docker compose up -d neo4j qdrant redis postgres
```

Wait ~30 seconds for services to initialize, then:

```bash
# Verify services are up
docker compose ps
```

### 3. Install Python Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 4. Run Database Migrations

```bash
cd backend
alembic upgrade head
```

### 5. Start Backend Services

```bash
# Terminal 1: API Server
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2: Celery Worker
cd backend
celery -A app.worker.celery_app worker --loglevel=info

# Terminal 3: Celery Beat (scheduler)
cd backend
celery -A app.worker.celery_app beat --loglevel=info
```

### 6. Start Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### 7. Ingest a Repository

```bash
# Ingest a local git repo
curl -X POST http://localhost:8000/api/v1/ingest/repository \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/your/repo", "name": "my-project"}'

# Or ingest a GitHub repo
curl -X POST http://localhost:8000/api/v1/ingest/github \
  -H "Content-Type: application/json" \
  -d '{"owner": "org", "repo": "repo-name", "github_token": "ghp_..."}'
```

### 8. Query the Knowledge Base

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Why was Redis chosen over Memcached for caching?", "repo_name": "my-project"}'
```

## Environment Variables

See `.env.example` for all configuration options. Key variables:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for LLM synthesis |
| `GITHUB_TOKEN` | GitHub personal access token |
| `NEO4J_URI` | Neo4j connection URI |
| `QDRANT_HOST` | Qdrant vector store host |
| `USE_OLLAMA` | Set to `true` to use Ollama instead of OpenAI |

## Architecture

```
backend/
  app/
    api/          # FastAPI route handlers
    ingestion/    # Git, GitHub, file ingestion workers
    graph/        # Neo4j knowledge graph operations
    vector/       # Qdrant vector store operations
    llm/          # LLM synthesis (OpenAI/Ollama)
    models/       # SQLAlchemy + Pydantic models
    worker/       # Celery task definitions
frontend/
  src/
    app/          # Next.js App Router pages
    components/   # React components
    lib/          # API client, utilities
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ingest/repository` | Ingest local git repo |
| POST | `/api/v1/ingest/github` | Ingest GitHub repository |
| GET | `/api/v1/ingest/status/{job_id}` | Check ingestion status |
| POST | `/api/v1/query` | Ask a question |
| GET | `/api/v1/graph/nodes` | Browse knowledge graph nodes |
| GET | `/api/v1/graph/search` | Search graph |
| GET | `/api/v1/repositories` | List ingested repositories |
| GET | `/api/v1/health` | Health check |

## VS Code Extension

```bash
cd vscode-extension
npm install
npm run compile
# Press F5 to launch extension development host
```

Use `Ctrl+Shift+P` → "Ask Codebase" to query from VS Code.