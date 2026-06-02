# Flaky Test Root-Cause Attribution & Self-Healing MVP

## Overview

This MVP demonstrates an automated system that:
1. **Ingests** CI/CD test execution events via webhooks
2. **Detects** flaky tests using statistical analysis (run-length encoding + pass/fail ratio)
3. **Classifies** root causes: timing, concurrency, environment, or state-leakage
4. **Assembles** scoped code context from repositories
5. **Synthesizes** fix proposals via GPT-4o (or mock mode)
6. **Delivers** fix proposals and surfaces a developer dashboard

## Architecture

```
CI Systems → Ingestion API (FastAPI) → PostgreSQL/TimescaleDB
                                     → Flakiness Detector (Python)
                                       → Root-Cause Classifier (DistilBERT + rules)
                                         → Context Assembler (AST/tree-sitter)
                                           → Fix Synthesizer (GPT-4o / mock)
                                             → PR Bot + Dashboard (React)
```

## Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- OpenAI API key (optional — system runs in mock mode without it)
- GitHub token (optional — for PR bot)

## Quick Start

### 1. Clone & Configure

```bash
cd flaky-test-detector
cp .env.example .env
# Edit .env with your API keys (optional for mock mode)
```

### 2. Start Infrastructure

```bash
docker-compose up -d postgres redis
```

### 3. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Initialize Database

```bash
cd backend
python -m app.db.init_db
```

### 5. Start Backend Services

```bash
# Terminal 1: API Server
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2: Flakiness Detection Worker
cd backend
python -m app.workers.flakiness_worker

# Terminal 3: Fix Synthesis Worker
cd backend
python -m app.workers.fix_worker
```

### 6. Start Frontend Dashboard

```bash
cd frontend
npm install
npm run dev
# Dashboard at http://localhost:5173
```

### 7. Ingest Sample Data

```bash
cd backend
python scripts/seed_demo_data.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/events/ingest` | Ingest CI test execution event |
| GET | `/api/v1/tests/flaky` | List detected flaky tests |
| GET | `/api/v1/tests/{id}/analysis` | Get root-cause analysis |
| GET | `/api/v1/fixes` | List proposed fixes |
| POST | `/api/v1/fixes/{id}/feedback` | Submit accept/reject feedback |
| GET | `/api/v1/repos` | List tracked repositories |
| GET | `/api/v1/dashboard/stats` | Dashboard statistics |
| WebSocket | `/ws/events` | Real-time event stream |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://...` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `OPENAI_API_KEY` | OpenAI API key (optional) | — |
| `GITHUB_TOKEN` | GitHub PAT for PR bot (optional) | — |
| `MOCK_LLM` | Use mock LLM responses | `true` |
| `MOCK_GITHUB` | Use mock GitHub PR creation | `true` |

## Sending Test Events

```bash
curl -X POST http://localhost:8000/api/v1/events/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "myorg/myrepo",
    "branch": "main",
    "commit_sha": "abc123",
    "pipeline_id": "run-456",
    "test_name": "test_user_login",
    "test_file": "tests/test_auth.py",
    "status": "failed",
    "duration_ms": 5234,
    "log_output": "TimeoutError: Expected element to appear within 2000ms",
    "ci_system": "github_actions"
  }'
```

## Demo Flow

1. Seed demo data: `python scripts/seed_demo_data.py`
2. Open dashboard: `http://localhost:5173`
3. View detected flaky tests with confidence scores
4. Click a test to see root-cause attribution
5. View generated fix proposals
6. Accept/reject fixes to trigger feedback loop