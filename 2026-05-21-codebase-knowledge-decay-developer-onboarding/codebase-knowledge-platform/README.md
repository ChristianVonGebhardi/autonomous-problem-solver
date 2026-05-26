# Codebase Knowledge Intelligence Platform

An AI-powered knowledge graph that mines git history, PRs, and code to build a queryable, living intelligence layer over any codebase.

## Architecture

- **Backend:** FastAPI (Python) with async workers
- **Graph DB:** Neo4j (relationships between files, authors, decisions)
- **Vector Store:** Qdrant (semantic similarity search)
- **Embeddings:** sentence-transformers
- **Code Chunking:** tree-sitter
- **LLM:** OpenAI GPT-4o (with mock fallback)
- **Task Queue:** Celery + Redis
- **Frontend:** Next.js web app
- **Cache:** Redis

## Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for frontend)
- Python 3.11+
- OpenAI API Key (optional — mock mode available)
- GitHub Personal Access Token (optional — for PR ingestion)

## Quick Start

### 1. Clone and configure

```bash
git clone <repo>
cd codebase-knowledge-platform
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start infrastructure services

```bash
docker compose up -d neo4j qdrant redis postgres
```

Wait ~30 seconds for Neo4j to initialize.

### 3. Install Python dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Run database migrations

```bash
cd backend
alembic upgrade head
```

### 5. Start the backend API

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 6. Start the Celery worker (new terminal)

```bash
cd backend
source venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info
```

### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## Ingesting a Repository

### Via API

```bash
# Ingest a local git repo
curl -X POST http://localhost:8000/api/v1/ingest/git \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/path/to/your/repo", "repo_name": "my-project"}'

# Ingest a GitHub repo (requires GITHUB_TOKEN in .env)
curl -X POST http://localhost:8000/api/v1/ingest/github \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/owner/repo", "repo_name": "my-project"}'
```

### Via Web UI

1. Go to http://localhost:3000
2. Click "Add Repository"
3. Enter repo path or GitHub URL
4. Watch ingestion progress

## Querying

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Why was the authentication system redesigned?", "repo_name": "my-project"}'
```

### Via Web UI

Use the chat interface at http://localhost:3000/query

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | (mock mode if absent) |
| `GITHUB_TOKEN` | GitHub Personal Access Token | optional |
| `NEO4J_URI` | Neo4j connection URI | bolt://localhost:7687 |
| `NEO4J_PASSWORD` | Neo4j password | password |
| `QDRANT_HOST` | Qdrant host | localhost |
| `REDIS_URL` | Redis connection URL | redis://localhost:6379 |
| `DATABASE_URL` | PostgreSQL URL | postgresql://... |

## Running Tests

```bash
cd backend
pytest tests/ -v
```

## Demo Mode

Set `DEMO_MODE=true` in `.env` to use pre-seeded sample data without needing a real repository.