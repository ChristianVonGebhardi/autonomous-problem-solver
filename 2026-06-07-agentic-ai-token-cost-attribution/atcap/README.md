# ATCAP — AI Token Cost Attribution Platform

A purpose-built instrumentation and analytics platform that intercepts LLM API calls, enriches them with business context, computes costs in real time, and correlates spend against business-value signals — turning opaque AI invoices into actionable ROI dashboards.

## Architecture Overview

```
SDK (Python)          Backend (FastAPI)        Frontend (React)
   │                       │                       │
   ├─ WorkflowContext  ─►  ├─ Token Events API     ├─ Overview Dashboard
   ├─ OpenAI Proxy    ─►  ├─ Cost Aggregation      ├─ Cost Breakdown
   └─ Anthropic Proxy ─►  ├─ Budget Policies       ├─ Budget Manager
                           ├─ ROI Correlation       ├─ ROI Correlation
                           ├─ Pricing Catalog       ├─ Alerts Panel
                           └─ Slack Alerting        └─ Pricing Catalog
```

**Storage:** SQLite (dev) → swap `DATABASE_URL` for PostgreSQL in production  
**Stack:** Python 3.11 + FastAPI + SQLAlchemy + React 18 + Recharts

---

## Quick Start (Docker Compose — recommended)

### Prerequisites
- Docker + Docker Compose v2

### 1. Clone and configure

```bash
cd atcap
cp backend/.env.example backend/.env
# Optionally edit backend/.env to add SLACK_WEBHOOK_URL, GITHUB_TOKEN, etc.
```

### 2. Start all services

```bash
docker compose up --build
```

Services started:
- **Backend API:** http://localhost:8000
- **Frontend Dashboard:** http://localhost:3000
- **API Docs (Swagger):** http://localhost:8000/docs

### 3. Run the demo to seed data

In a second terminal:

```bash
cd atcap/backend
pip install httpx  # if not already installed
python -m demo.run_demo
```

This seeds 30 days of synthetic LLM call data, business value events, and budget policies, then prints a summary of costs by team and model.

### 4. Open the dashboard

Navigate to **http://localhost:3000** to explore:
- **Overview** — total costs, team breakdown, time series, budget utilisation
- **Cost Breakdown** — drill by team, feature, model, or top events
- **Budget Policies** — create/manage spend thresholds with warn/critical alerts
- **Alerts** — view and acknowledge triggered budget alerts
- **ROI Correlation** — correlate token spend against business value outcomes
- **Pricing Catalog** — view and update LLM pricing rates

---

## Local Development (no Docker)

### Backend

```bash
cd atcap/backend

# Create virtualenv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env as needed (SQLite is the default, no extra setup required)

# Start backend
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd atcap/frontend

npm install
npm start
# Opens http://localhost:3000
```

### Run demo

```bash
cd atcap/backend
python -m demo.run_demo
```

---

## SDK Usage

The Python SDK wraps LLM clients to automatically emit cost events with attribution context.

### Installation

```bash
# From the backend directory (SDK is co-located)
# Or install as a package in future: pip install atcap-sdk
```

### OpenAI

```python
import openai
import sys
sys.path.insert(0, 'path/to/atcap/backend')

from sdk import instrument_openai, WorkflowContext

# Wrap your OpenAI client once at startup
client = instrument_openai(
    openai.OpenAI(api_key="sk-..."),
    collector_url="http://localhost:8000"
)

# Set attribution context before each workflow
with WorkflowContext(
    team="platform",
    feature="code-review-agent",
    business_entity_id="PR-1234",
    business_entity_type="pr"
):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Review this code..."}]
    )
    # Cost automatically attributed to platform/code-review-agent/PR-1234
```

### Anthropic

```python
import anthropic
from sdk import instrument_anthropic, WorkflowContext

client = instrument_anthropic(
    anthropic.Anthropic(api_key="sk-ant-..."),
    collector_url="http://localhost:8000"
)

with WorkflowContext(team="search", feature="query-expansion"):
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Expand this query..."}]
    )
```

### Manual event ingestion (direct API)

```bash
curl -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{
    "team": "search",
    "feature": "ai-search",
    "provider": "openai",
    "model": "gpt-4o",
    "prompt_tokens": 1200,
    "completion_tokens": 400,
    "business_entity_id": "JIRA-4567",
    "business_entity_type": "ticket"
  }'
```

### Batch ingestion

```bash
curl -X POST http://localhost:8000/api/v1/events/batch \
  -H "Content-Type: application/json" \
  -d '{"events": [...]}'
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/events` | Ingest a single token event |
| POST | `/api/v1/events/batch` | Ingest multiple events |
| GET | `/api/v1/costs/summary` | Aggregated cost summary |
| GET | `/api/v1/costs/by-team` | Cost breakdown by team |
| GET | `/api/v1/costs/by-feature` | Cost breakdown by feature |
| GET | `/api/v1/costs/by-model` | Cost breakdown by model |
| GET | `/api/v1/costs/timeseries` | Time series cost data |
| GET | `/api/v1/costs/top-events` | Most expensive calls |
| GET | `/api/v1/budgets` | List budget policies |
| POST | `/api/v1/budgets` | Create budget policy |
| DELETE | `/api/v1/budgets/{id}` | Remove budget policy |
| POST | `/api/v1/budgets/evaluate` | Trigger policy evaluation |
| GET | `/api/v1/alerts` | List triggered alerts |
| POST | `/api/v1/alerts/{id}/acknowledge` | Acknowledge an alert |
| GET | `/api/v1/roi` | ROI correlation records |
| POST | `/api/v1/roi/compute` | Trigger ROI computation |
| POST | `/api/v1/value-events` | Ingest a value event |
| GET | `/api/v1/value-events` | List value events |
| GET | `/api/v1/pricing` | List pricing catalog |
| POST | `/api/v1/pricing` | Add/update pricing entry |
| POST | `/api/v1/alerts/test` | Send test Slack alert |

Full interactive docs: http://localhost:8000/docs

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./atcap.db` | Database connection string |
| `REDIS_URL` | — | Redis URL (optional, reserved for future) |
| `SECRET_KEY` | `dev-secret-...` | JWT secret (for future auth) |
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook for alerts |
| `GITHUB_TOKEN` | — | GitHub PAT for PR ingestion |
| `GITHUB_ORG` | — | GitHub org for auto-repo discovery |
| `JIRA_BASE_URL` | — | Jira instance URL |
| `JIRA_TOKEN` | — | Jira API token |
| `DEFAULT_BUDGET_ALERT_THRESHOLD_PCT` | `80.0` | Default warn threshold |

---

## Production Deployment

### Switch to PostgreSQL

```bash
# In backend/.env:
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/atcap
```

Add `asyncpg` to requirements.txt:
```
asyncpg==0.29.0
```

### Scale considerations

- The current SQLite backend handles dev/demo workloads well
- For production ingestion volumes (>100 events/sec), migrate to PostgreSQL + add a Redis write-behind buffer
- The architecture is designed to slot Kafka in front of the ingest path with minimal code changes
- ClickHouse can replace the `cost_aggregates` table for sub-second dashboard queries at scale

---

## Budget Alerting

Budget policies are evaluated:
1. **Automatically** every 60 seconds in the background
2. **On demand** via `POST /api/v1/budgets/evaluate` or the dashboard button

Alert levels:
- **Warning** — spend ≥ `warn_threshold_pct` (default 80%)
- **Critical** — spend ≥ `critical_threshold_pct` (default 95%)

Alerts fire at most once per hour per policy to prevent spam. Configure `SLACK_WEBHOOK_URL` to receive Slack notifications.

---

## CI Cost Gate (OPA / Conftest)

To enforce AI cost budgets in CI pipelines:

```bash
# Check current spend against policy before deployment
curl http://localhost:8000/api/v1/budgets | \
  jq '[.[] | select(.spend_pct > 90)] | length' | \
  xargs -I {} sh -c 'if [ {} -gt 0 ]; then echo "COST GATE FAILED"; exit 1; fi'
```

A full OPA/conftest integration can be layered on top of the REST API for more complex gate logic.