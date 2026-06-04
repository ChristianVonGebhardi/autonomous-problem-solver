# Codebase Knowledge Intelligence Platform

An AI-powered knowledge graph that mines git history, PRs, and code to build a queryable, living intelligence layer over any codebase. Developers ask natural-language questions and get contextually-grounded answers tied to specific files, commits, and decisions.

## Architecture

- **Backend:** FastAPI (Python 3.11) + Celery workers for async ingestion
- **Graph DB:** Neo4j — stores file/commit/author/PR relationships  
- **Vector Store:** Qdrant — semantic similarity search over code chunks
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2`
- **LLM:** OpenAI GPT-4o (falls back to mock mode if no key)
- **Frontend:** Next.js 14 (App Router) + Tailwind CSS
- **Queue:** Celery + Redis

## Prerequisites

- Docker & Docker Compose v2
- (Optional) OpenAI API key for AI-synthesized answers
- (Optional) GitHub token for private repo ingestion

## Quick Start

### 1. Clone and configure

```bash
cd codebase-knowledge-platform
cp .env.example .env
```

Edit `.env` and set at minimum:
```env
OPENAI_API_KEY=sk-...          # Optional but recommended
GITHUB_TOKEN=ghp_...           # Optional, for private GitHub repos
```

### 2. Start all services

```bash
docker compose up --build
```

This starts:
- **Neo4j** on http://localhost:7474 (browser) and bolt://localhost:7687
- **Qdrant** on http://localhost:6333
- **Redis** on localhost:6379
- **PostgreSQL** on localhost:5432
- **Backend API** on http://localhost:8000
- **Frontend** on http://localhost:3000
- **Celery Worker** (background ingestion)

Wait ~60 seconds for all services to initialize (Neo4j takes the longest).

### 3. Open the app

Visit **http://localhost:3000**

## Usage

### Ingest a Repository

**Option A — Local repo (fastest for development):**

The repo must be mounted into the backend container. By default the current directory is available. To ingest a repo accessible from the container:

```bash
# Add a volume to docker-compose.yml backend service:
# volumes:
#   - /path/to/your/repo:/repos/myrepo

# Then ingest via UI at http://localhost:3000/ingest
# Or via API:
curl -X POST http://localhost:8000/api/v1/ingest/git \
  -H 'Content-Type: application/json' \
  -d '{"repo_path": "/repos/myrepo", "repo_name": "myrepo"}'
```

**Option B — GitHub URL:**

```bash
curl -X POST http://localhost:8000/api/v1/ingest/github \
  -H 'Content-Type: application/json' \
  -d '{"repo_url": "https://github.com/owner/repo", "repo_name": "my-repo"}'
```

**Option C — Ingest via UI:**  
Navigate to http://localhost:3000/ingest and fill in the form.

### Query the Codebase

Once ingestion is complete (status = "ready"):

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"question": "How is authentication implemented?", "repo_name": "my-repo"}'
```

Or use the chat UI at **http://localhost:3000/query**.

### Explore the Knowledge Graph

Visit **http://localhost:3000/graph** to see a force-directed graph of file relationships, commit authors, and PRs.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | System health check |
| POST | `/api/v1/ingest/git` | Ingest local git repo |
| POST | `/api/v1/ingest/github` | Clone & ingest GitHub repo |
| GET | `/api/v1/ingest/jobs/{id}` | Get ingestion job status |
| GET | `/api/v1/ingest/repositories` | List all repositories |
| POST | `/api/v1/query` | Ask a natural language question |
| GET | `/api/v1/query/history` | Get query history |
| GET | `/api/v1/graph/{repo}/visualization` | Graph visualization data |
| GET | `/api/v1/graph/{repo}/stats` | Repository statistics |
| GET | `/api/v1/graph/{repo}/file-history` | File commit history |

Interactive API docs: **http://localhost:8000/docs**

## Development Setup (without Docker)

### Backend

```bash
cd backend

# Create virtualenv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure env
cp ../.env.example .env
# Edit .env with your local service URLs

# Start services (Neo4j, Qdrant, Redis, PostgreSQL must be running)
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

npm install
cp ../.env.example .env.local
# Set NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
```

### Run Tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI key (optional, falls back to mock) |
| `OPENAI_MODEL` | `gpt-4o` | Model to use |
| `GITHUB_TOKEN` | — | GitHub PAT for private repos |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |
| `DEMO_MODE` | `false` | Enable demo mode |

## Without OpenAI API Key

The platform works in **mock mode** without an OpenAI key:
- Repository ingestion, chunking, embedding, and graph building work fully
- Queries return the retrieved code chunks with a mock answer explaining what would be synthesized
- Set `OPENAI_API_KEY` in `.env` to enable full AI-powered answers

## Architecture Notes

### Ingestion Pipeline
1. Git worker extracts commits, file tree, and blame data → Neo4j knowledge graph
2. Code chunker (regex-based structural parser) splits files into semantic chunks
3. Sentence transformer generates 384-dim embeddings for each chunk
4. Chunks + embeddings stored in Qdrant; file/commit nodes stored in Neo4j

### Query Pipeline
1. Question embedded with same model
2. Qdrant semantic search returns top-K chunks
3. Neo4j traversal finds related files, commit history, and co-change patterns
4. Hybrid results merged and ranked
5. GPT-4o synthesizes a grounded answer citing source files
6. Response cached in Redis (10 min TTL)

## Troubleshooting

**Neo4j not connecting:**
```bash
docker compose logs neo4j
# Wait for "Started." in logs, then retry
```

**Embedding model download slow on first run:**
The `all-MiniLM-L6-v2` model (~90MB) is downloaded on first use. Subsequent starts are instant.

**Celery not processing jobs:**
```bash
docker compose logs celery_worker
# Check Redis connectivity
```

**Frontend can't reach backend:**
Ensure `NEXT_PUBLIC_API_URL=http://localhost:8000` in your frontend env.