# ATCAP — AI Token Cost Attribution Platform

## Overview

ATCAP is a purpose-built instrumentation and analytics platform that intercepts LLM API calls, enriches them with business context, stores cost/usage telemetry, and correlates spend against business-value signals through real-time dashboards.

## Architecture (MVP)

```
Python SDK → FastAPI Collector → PostgreSQL/ClickHouse-compatible SQLite → React Dashboard
                ↓
         Background Processor (cost enrichment, windowed rollups)
                ↓
         Business Value Ingestion (GitHub webhooks, Jira mock)
                ↓
         Slack Alerting (budget breach notifications)
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional, for full stack)

## Quick Start

### 1. Clone and set up the project

```bash
cd atcap
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env with your settings (optional for MVP demo)

# Initialize database
python -m app.db.init_db

# Start the backend
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm start
# Opens at http://localhost:3000
```

### 4. Run the Demo SDK

```bash
cd backend
# In a separate terminal (with venv activated)
python -m demo.run_demo
```

This simulates multiple AI agents making LLM calls with business context tags, generating cost data visible in the dashboard.

## Docker Compose (Full Stack)

```bash
docker-compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

## Key Features Demonstrated

1. **SDK Instrumentation**: `WorkflowContext` propagator + LLM client interceptor
2. **Real-time Cost Computation**: Token counts × per-model pricing
3. **Attribution**: Costs tagged by team, feature, workflow, business entity
4. **Budget Policies**: Configurable per-team/feature thresholds with breach alerts
5. **Business Value Correlation**: Link costs to GitHub PRs, Jira tickets
6. **Dashboard**: React UI with Recharts — cost by team, model, feature, ROI
7. **REST API**: Full CRUD for policies, budget queries, cost reports

## API Endpoints

- `POST /api/v1/events` — Ingest token usage events from SDK
- `GET /api/v1/costs/summary` — Aggregated cost summary
- `GET /api/v1/costs/by-team` — Costs broken down by team
- `GET /api/v1/costs/by-feature` — Costs broken down by feature
- `GET /api/v1/costs/by-model` — Costs broken down by model
- `GET /api/v1/budgets` — List budget policies
- `POST /api/v1/budgets` — Create budget policy
- `GET /api/v1/roi` — ROI correlation records
- `POST /api/v1/value-events` — Ingest business value events
- `GET /api/v1/pricing` — Current pricing catalog
- `POST /api/v1/alerts/test` — Test Slack alert

## Pricing Catalog

Versioned pricing stored in `backend/app/data/pricing_catalog.json`. Models supported:
- OpenAI: gpt-4o, gpt-4-turbo, gpt-3.5-turbo, o1, o1-mini
- Anthropic: claude-3-5-sonnet, claude-3-opus, claude-3-haiku
- Google: gemini-1.5-pro, gemini-1.5-flash

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./atcap.db` | Database connection string |
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook for alerts |
| `GITHUB_TOKEN` | — | GitHub API token for value ingestion |
| `JIRA_BASE_URL` | — | Jira instance URL |
| `JIRA_TOKEN` | — | Jira API token |
| `SECRET_KEY` | `dev-secret` | JWT secret for API auth |