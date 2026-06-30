# Agentic AI Workflow Behavioral Drift Detection

A behavioral telemetry and drift detection platform for enterprise agentic AI workflows. Detects when pipelines silently deviate from intended behavior across three signal layers: **structural** (tool selection sequences), **semantic** (embedding-space distance), and **distributional** (output distributions via CUSUM/EWMA).

## Architecture (MVP)

```
Agent Runtime → BehaviorTrace SDK → SQLite Queue → Drift Detection Workers → TimescaleDB/SQLite
                                                                                    ↓
                                                                          FastAPI Control Plane
                                                                                    ↓
                                                                          React Dashboard
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (for TimescaleDB + Qdrant)
- OpenAI API key (optional — for LLM explainability on alerts)

## Quick Start

### 1. Start Infrastructure

```bash
cd drift-detector
docker-compose up -d
```

This starts:
- TimescaleDB (PostgreSQL + time-series extension) on port 5432
- Qdrant vector store on port 6333
- Redis on port 6379

### 2. Install Python Dependencies

```bash
cd drift-detector
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL, QDRANT_URL, and optionally OPENAI_API_KEY
```

### 4. Initialize Database

```bash
python -m backend.db.init_db
```

### 5. Start the Backend API

```bash
uvicorn backend.api.main:app --reload --port 8000
```

### 6. Start the Drift Detection Worker

```bash
python -m backend.workers.drift_worker
```

### 7. Start the React Dashboard

```bash
cd dashboard
npm install
npm start
# Opens at http://localhost:3000
```

### 8. Run the Demo

```bash
# In a separate terminal with venv activated
python demo/run_demo.py
```

This simulates a multi-step agentic workflow, injects drift after baseline runs, and shows detection in the dashboard.

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
drift-detector/
├── sdk/                    # BehaviorTrace instrumentation SDK
│   ├── __init__.py
│   ├── tracer.py           # OTEL-compatible span capture
│   ├── enricher.py         # Async embedding + metadata enrichment
│   └── adapters/           # LangChain, generic adapters
├── backend/
│   ├── api/                # FastAPI control plane
│   ├── workers/            # Drift detection workers
│   ├── detection/          # CUSUM, EWMA, structural, semantic analyzers
│   ├── db/                 # TimescaleDB schema + queries
│   └── models/             # Pydantic data models
├── dashboard/              # React frontend
├── demo/                   # Demo scripts
├── tests/                  # Test suite
├── docker-compose.yml
└── requirements.txt
```

## Key Concepts

- **Golden Runs**: Human-approved baseline traces. Curate via `POST /api/workflows/{id}/baselines`
- **Drift Score**: Weighted composite of structural (0-1), semantic (0-1), and distributional (0-1) signals
- **CUSUM**: Cumulative sum control chart — detects sustained shifts in output distributions
- **EWMA**: Exponentially weighted moving average — smooths noise, surfaces trends
- **Semantic Baseline**: Centroid embedding of golden run reasoning chains in Qdrant

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/workflows` | Register a workflow |
| GET | `/api/workflows` | List workflows |
| POST | `/api/traces` | Ingest a behavioral trace |
| GET | `/api/traces/{workflow_id}` | Get traces for workflow |
| POST | `/api/baselines/{workflow_id}` | Promote trace to baseline |
| GET | `/api/drift/{workflow_id}` | Get drift scores timeline |
| GET | `/api/alerts` | List active alerts |
| GET | `/api/drift/{workflow_id}/latest` | Latest drift score |