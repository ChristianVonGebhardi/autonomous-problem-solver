# Flaky Test Root-Cause Attribution & Self-Healing System

An automated platform that detects flaky CI/CD tests, classifies their root causes (timing, concurrency, environment, state leakage), and proposes targeted code-level fixes — operating as a background service that augments existing pipelines without replacing them.

## What it does

1. **Ingests** test execution events from GitHub Actions, GitLab CI, Jenkins, CircleCI via webhooks or direct API calls
2. **Detects flakiness** statistically using run-length encoding, alternation rate analysis, entropy scoring, and a KS-test variant on pass/fail distributions
3. **Classifies root causes** using a two-tier approach: fast rule-based regex matching with a DistilBERT/NLI ML classifier as enhancement
4. **Assembles scoped context** using a FlakyGuard-inspired AST traversal — extracting only the relevant code sections (fixture definitions for state leakage, timing calls for timing issues, etc.) to avoid LLM context bloat
5. **Synthesizes fixes** via GPT-4o (or mock mode) that generate unified diff patches with explanations
6. **Opens PRs** on GitHub/GitLab with rich context: confidence score, evidence, diff preview
7. **Learns from feedback**: accept/reject signals on PRs feed back into the classifier retraining pipeline
8. **Streams real-time updates** to the dashboard via WebSocket

## Architecture

```
CI Events → Ingestion API (FastAPI) → Redis Queue
                                          ↓
                              Flakiness Worker (Python)
                              ├── Statistical detection (KS-test, RLE)
                              ├── Root-cause classifier (DistilBERT + rules)
                              └── Fix synthesis queue
                                          ↓
                              Fix Worker (Python)
                              ├── Context assembler (AST-scoped)
                              ├── LLM fix synthesis (GPT-4o / mock)
                              └── PR Bot (GitHub/GitLab)
                                          ↓
                              Dashboard (React + FastAPI)
                              └── Real-time WebSocket stream
```

Data is stored in PostgreSQL (with TimescaleDB for time-series hypertables when available). Redis handles job queuing and pub/sub for real-time updates.

## Prerequisites

- Docker & Docker Compose (for Postgres + Redis)
- Python 3.11+
- Node.js 18+
- An OpenAI API key (optional — system runs in mock mode without it)
- A GitHub token (optional — PRs are mocked without it)

## Quick Start

### 1. Clone and configure

```bash
git clone <repo>
cd flaky-test-detector
cp .env.example .env
# Edit .env — at minimum, the defaults work for local dev
```

### 2. Start infrastructure

```bash
docker compose up postgres redis -d
# Wait for them to be healthy (about 10 seconds)
```

### 3. Set up the Python backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> **Note on torch**: `torch==2.3.0` is a large package (~800MB). If you want to skip ML classification and use only the rule-based classifier, you can remove the `torch` and `transformers` lines from `requirements.txt` — the system gracefully falls back.

### 4. Initialize the database

```bash
python -m app.db.init_db
# or
python backend/app/db/init_db.py
```

### 5. Seed demo data

```bash
python scripts/seed_demo_data.py
```

This creates 3 repositories, 15 flaky tests with 20–30 historical runs each, root cause analyses, and fix proposals — enough to explore the full dashboard.

### 6. Start the backend API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7. Start the workers (separate terminals)

```bash
# Terminal 2: Flakiness detection worker
python -m app.workers.flakiness_worker

# Terminal 3: Fix synthesis worker
python -m app.workers.fix_worker
```

### 8. Start the frontend

```bash
cd ../frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

## Using Docker Compose (full stack)

```bash
# Build and start everything
docker compose up --build

# In another terminal, seed demo data
docker compose exec backend python scripts/seed_demo_data.py
```

Then open http://localhost:5173 for the dashboard and http://localhost:8000/docs for the API.

## Configuration

All settings are in `.env`. Key options:

| Variable | Default | Description |
|---|---|---|
| `MOCK_LLM` | `true` | Use template fixes instead of OpenAI API |
| `OPENAI_API_KEY` | _(empty)_ | Required for real LLM fix synthesis |
| `LLM_MODEL` | `gpt-4o` | OpenAI model to use |
| `MOCK_GITHUB` | `true` | Simulate PR creation instead of real GitHub API |
| `GITHUB_TOKEN` | _(empty)_ | Required for real PR creation |
| `FLAKINESS_THRESHOLD` | `0.3` | Minimum flakiness score (0-1) to flag a test |
| `MIN_RUNS_FOR_DETECTION` | `3` | Minimum runs before flakiness analysis |
| `CONFIDENCE_THRESHOLD` | `0.6` | Minimum classification confidence to trigger fix synthesis |

## Sending test events

### Via the dashboard

Go to **Ingest Event** in the sidebar. Use the example buttons to load pre-filled events, then click **Send Event**.

Use **Batch Ingest** to send multiple events for the same test with mixed pass/fail statuses — this triggers flakiness detection (requires >3 runs).

### Via the API

```bash
curl -X POST http://localhost:8000/api/v1/events/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "myorg/myrepo",
    "branch": "main",
    "commit_sha": "abc123",
    "test_name": "tests/test_auth.py::TestAuth::test_login",
    "test_file": "tests/test_auth.py",
    "status": "failed",
    "duration_ms": 5200,
    "log_output": "TimeoutError: Expected element within 2000ms",
    "error_message": "TimeoutError after 5200ms",
    "ci_system": "github_actions"
  }'
```

### Triggering a fix manually

From the Flaky Test detail page, click **Generate Fix**. Or via API:

```bash
curl -X POST http://localhost:8000/api/v1/fixes/trigger/{flaky_test_id}
```

## API Docs

Interactive Swagger UI: http://localhost:8000/docs  
ReDoc: http://localhost:8000/redoc

Key endpoints:

| Endpoint | Description |
|---|---|
| `POST /api/v1/events/ingest` | Ingest a test execution event |
| `POST /api/v1/events/ingest/batch` | Ingest up to 1000 events |
| `GET /api/v1/flaky-tests` | List flaky tests (filter by repo, cause, active) |
| `GET /api/v1/flaky-tests/{id}` | Get test detail + run history |
| `GET /api/v1/fixes` | List fix proposals (filter by status) |
| `POST /api/v1/fixes/{id}/feedback` | Submit accept/reject feedback |
| `POST /api/v1/fixes/trigger/{test_id}` | Trigger fix synthesis |
| `GET /api/v1/dashboard/stats` | Dashboard statistics |
| `GET /api/v1/dashboard/trends` | Time-series trend data |
| `POST /api/v1/analyses/classify` | On-demand failure classification |
| `WS /ws/events` | WebSocket real-time event stream |

## Enabling real OpenAI fix synthesis

1. Set `OPENAI_API_KEY=sk-...` in `.env`
2. Set `MOCK_LLM=false`
3. Restart the fix worker

The fix worker will call GPT-4o with:
- Scoped code context (AST-extracted, cause-specific)
- Failure evidence from logs
- Fix templates for the identified root cause category
- Structured JSON output request

## Enabling real GitHub PRs

1. Create a GitHub Personal Access Token with `repo` scope
2. Set `GITHUB_TOKEN=ghp_...` in `.env`
3. Set `MOCK_GITHUB=false`
4. Restart the fix worker

PRs are opened on the target repository with: diff preview, confidence score, explanation, and instructions for accepting or rejecting.

## Root Cause Categories

| Cause | Detection Signals | Fix Strategy |
|---|---|---|
| **Timing** | `timeout`, `sleep`, `waited`, `elapsed` | Replace sleeps with polling waits, increase timeouts |
| **Concurrency** | `race condition`, `ThreadSanitizer`, `deadlock`, `mutex` | Add locks, use thread-safe structures |
| **Environment** | `ECONNREFUSED`, `FileNotFound`, `NoBrokersAvailable` | Mock external deps, add retries |
| **State Leakage** | `UniqueViolation`, `duplicate key`, `leftover data` | Add DB rollback fixtures, reset global state |

## Development

### Running tests

```bash
cd backend
pytest tests/ -v
```

### Linting the frontend

```bash
cd frontend
npm run lint
```

### Database schema

```bash
# Apply schema manually
python -c "from app.db.init_db import init_database; init_database()"

# Reset (drops nothing — schema is idempotent with IF NOT EXISTS)
python -c "from app.db.init_db import init_database; init_database()"
```

## Project Structure

```
flaky-test-detector/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI route handlers
│   │   │   ├── events.py         # Ingestion endpoints
│   │   │   ├── flaky_tests.py    # Flaky test CRUD
│   │   │   ├── fixes.py          # Fix proposal endpoints
│   │   │   ├── analyses.py       # Root cause analysis endpoints
│   │   │   ├── dashboard.py      # Stats + trends
│   │   │   └── websocket.py      # Real-time WebSocket
│   │   ├── db/             # Database setup and models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # Core ML/analysis services
│   │   │   ├── flakiness_detector.py    # Statistical detection
│   │   │   ├── root_cause_classifier.py # Rule-based + ML classifier
│   │   │   ├── context_assembler.py     # AST-scoped context
│   │   │   ├── fix_synthesizer.py       # LLM fix generation
│   │   │   └── pr_bot.py               # GitHub/GitLab PR creation
│   │   └── workers/        # Background workers
│   │       ├── flakiness_worker.py  # Detection + classification
│   │       └── fix_worker.py        # Fix synthesis + PR creation
│   ├── scripts/
│   │   └── seed_demo_data.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/          # Dashboard, FlakyTests, Fixes, Ingest
│       ├── components/     # Reusable UI components
│       ├── hooks/          # useWebSocket
│       └── api.ts          # API client
├── docker-compose.yml
├── .env.example
└── README.md
```