# Codebase Knowledge Intelligence Platform

An AI-powered knowledge graph that mines git history, PRs, and code to build a queryable, living intelligence layer over any codebase. Developers ask natural-language questions and receive contextually-grounded answers tied to specific files, commits, and decisions.

## Architecture

- **Backend:** FastAPI (Python 3.11) + Celery workers
- **Graph DB:** Neo4j 5 — files, authors, commits, PRs, relationships
- **Vector Store:** Qdrant — semantic similarity search over code chunks
- **Embeddings:** `sentence-transformers` (all-MiniLM-L6-v2, runs locally)
- **LLM:** OpenAI GPT-4o (optional; falls back to mock mode without a key)
- **Task Queue:** Celery + Redis
- **Frontend:** Next.js 14 + TailwindCSS
- **Metadata DB:** PostgreSQL

## Prerequisites

- Docker & Docker Compose (v2+)
- Git
- (Optional) OpenAI API key for AI-synthesized answers
- (Optional) GitHub token for ingesting private repos and PR data

## Quick Start

### 1. Clone & configure

```bash
git clone <this-repo>
cd codebase-knowledge-platform

cp .env.example .env
```

Edit `.env` and set at minimum:

```env
# Required for AI-synthesized answers (optional — mock mode works without it)
OPENAI_API_KEY=sk-...

# Optional: for ingesting private GitHub repos and PR discussions
GITHUB_TOKEN=ghp_...
```

### 2. Start all services

```bash
docker compose up --build
```

This starts:
| Service | URL |
|---|---|
| Frontend (Next.js) | http://localhost:3000 |
| Backend API (FastAPI) | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 |
| Qdrant Dashboard | http://localhost:6333/dashboard |

First startup takes 3–5 minutes while Docker pulls images and the embedding model downloads (~90 MB).

### 3. Ingest a repository

#### Option A: Via the Web UI

1. Open http://localhost:3000
2. Click **Ingest Repository** in the sidebar
3. Choose **Local Repository** tab and enter an absolute path (the path must be accessible *inside* the backend container)
4. Or choose **GitHub Repository** and enter a GitHub HTTPS URL

#### Option B: Mount a local repo into the backend container

Edit `docker-compose.yml` to mount your repo:

```yaml
backend:
  volumes:
    - ./backend:/app
    - repo_cache:/tmp/repos
    - /path/to/your/local/repo:/repos/myrepo:ro   # add this line
```

Then restart: `docker compose up -d backend celery_worker`

Now ingest with path `/repos/myrepo` in the UI.

#### Option C: Via API

```bash
# Local repo (path must be accessible from the backend container)
curl -X POST http://localhost:8000/api/v1/ingest/git \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/repos/myrepo", "repo_name": "myrepo"}'

# GitHub repo
curl -X POST http://localhost:8000/api/v1/ingest/github \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/owner/repo", "repo_name": "repo"}'
```

### 4. Query your codebase

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What does the authentication module do?", "repo_name": "myrepo"}'
```

Or use the **Ask Codebase** page at http://localhost:3000/query.

## Running Tests

```bash
# Backend unit tests (no running services required)
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

## Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start infrastructure only
docker compose up neo4j qdrant redis postgres -d

# Run the API
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | _(empty)_ | OpenAI key — blank = mock mode |
| `OPENAI_MODEL` | `gpt-4o` | Model to use for synthesis |
| `GITHUB_TOKEN` | _(empty)_ | For private repos & PR ingestion |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |
| `NEO4J_USER` | `neo4j` | Neo4j user |
| `NEO4J_PASSWORD` | `password` | Neo4j password |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis / Celery broker |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL connection string |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model |
| `DEMO_MODE` | `false` | Enable demo seed data |
| `MAX_FILE_SIZE_KB` | `500` | Skip files larger than this |
| `CHUNK_SIZE_TOKENS` | `512` | Lines per chunk (approximate) |

## End-to-End Flow

1. **Ingest** → Git worker walks commits, files, and optionally PRs → chunks code → generates embeddings → stores in Neo4j (graph) + Qdrant (vectors)
2. **Query** → Embed question → semantic search in Qdrant → graph traversal in Neo4j for co-change/commit context → merge & rank → LLM synthesizes answer grounded in retrieved chunks
3. **Visualize** → Knowledge graph page renders file/author/commit/PR relationships as interactive force-directed graph

## Mock Mode (No OpenAI Key)

Without `OPENAI_API_KEY`, the system still:
- Ingests repositories and builds the knowledge graph
- Performs semantic vector search
- Returns the retrieved relevant code chunks
- Generates a structured mock answer showing what was found

Set `OPENAI_API_KEY` in `.env` and restart the backend to get AI-synthesized architectural explanations.

## API Reference

Full interactive docs: http://localhost:8000/docs

Key endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | System health check |
| `POST` | `/api/v1/ingest/git` | Ingest local repo |
| `POST` | `/api/v1/ingest/github` | Clone & ingest GitHub repo |
| `GET` | `/api/v1/ingest/jobs/{id}` | Job progress polling |
| `GET` | `/api/v1/ingest/repositories` | List all repos |
| `POST` | `/api/v1/query` | Natural-language query |
| `GET` | `/api/v1/query/history` | Query history |
| `GET` | `/api/v1/graph/{repo}/stats` | Graph statistics |
| `GET` | `/api/v1/graph/{repo}/visualization` | Graph for visualization |
| `GET` | `/api/v1/graph/{repo}/file-history` | File commit history |
| `GET` | `/api/v1/graph/{repo}/related-files` | Co-changed files |

## Troubleshooting

**Neo4j fails to start**
```bash
docker compose logs neo4j
# Usually needs more memory — increase Docker Desktop memory limit to 4GB+
```

**Embedding model download is slow**
The model is downloaded once and cached inside the container. Subsequent restarts are fast.

**`Path does not exist` when ingesting local repo**
The backend runs inside Docker. Mount the repo as a volume (see Option B above) or use GitHub ingestion.

**Celery tasks not processing**
```bash
docker compose logs celery_worker
# Or restart:
docker compose restart celery_worker
```

**Database schema errors**
```bash
docker compose down -v   # WARNING: deletes all data
docker compose up --build
```