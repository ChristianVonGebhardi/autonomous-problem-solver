# Behavioral Drift Detection Platform

A lightweight behavioral telemetry and drift detection platform for enterprise agentic AI workflows. Detects when production AI agents silently deviate from their intended behavior across three signal layers: **structural** (tool sequences), **semantic** (embedding-space reasoning), and **distributional** (CUSUM/EWMA confidence statistics).

## Architecture Overview

```
Agent Runtime → BehaviorTrace SDK → FastAPI (trace ingestion)
                                         ↓
                                   Drift Detection Worker
                                   ├── Structural Analyzer (edit distance)
                                   ├── Semantic Analyzer (sentence-transformers)
                                   └── Distributional Analyzer (CUSUM/EWMA)
                                         ↓
                                   PostgreSQL (TimescaleDB optional)
                                         ↓
                                   React Dashboard (drift timelines, alerts)
```

## Requirements

- Python 3.11+
- Node.js 18+ (for dashboard)
- PostgreSQL 14+ (TimescaleDB optional but recommended)
- 2 GB RAM (for local embedding model)

## Quick Start with Docker Compose

The fastest way to run everything:

```bash
cd behavioral-drift-detection
cp .env.example .env
docker-compose up -d
```

This starts:
- PostgreSQL on port 5432
- FastAPI on port 8000
- Drift detection worker
- React dashboard on port 5173

Then run the simulation:
```bash
pip install -r requirements.txt
python -m examples.simulate_agent
```

## Manual Setup

### 1. PostgreSQL

```bash
# macOS
brew install postgresql@15
brew services start postgresql@15
createdb drift_detection

# Ubuntu
sudo apt install postgresql
sudo -u postgres createdb drift_detection
```

Update `.env`:
```
DATABASE_URL=postgresql://localhost/drift_detection
```

### 2. Python Backend

```bash
cd behavioral-drift-detection
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Initialize database tables
python -m scripts.init_db
```

### 3. Start the API Server

```bash
uvicorn api.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 4. Start the Drift Detection Worker

In a separate terminal:

```bash
python -m workers.run_worker
```

The worker polls PostgreSQL every 2 seconds for unprocessed traces and runs the full detection pipeline.

### 5. Start the Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Dashboard available at: http://localhost:5173

## Running the Simulation

With all three components running (API, worker, dashboard):

```bash
python -m examples.simulate_agent
```

This demonstrates the full end-to-end flow:
1. Registers a "Customer Service Agent" workflow
2. Submits 3 golden-run traces and approves them as baselines
3. Submits 4 normal production runs (expect low drift scores)
4. Injects 6 progressively drifting runs (expect alerts)
5. Displays drift scores and severity classification

Expected output:
```
✓ API is up
✓ Workflow registered: <uuid>

── Phase 1: Submitting golden runs ──
  Submitted golden run 1: abc12345...

── Phase 2: Approving baselines ──
  Baseline approved: abc12345...

── Phase 3: Normal production runs ──
  Normal run 1: def67890...

── Phase 4: Injecting behavioral drift ──
  Drifted run 1: ghi11223...

── Phase 5: Workflow health summary ──
  Workflow: Customer Service Agent
  Recent composite score: 0.743
  Trend: increasing
  Alerts (24h): 4
```

## Running Tests

```bash
pytest tests/ -v
```

## SDK Usage

Instrument your own agent:

```python
from sdk.behavior_trace import BehaviorTracer

tracer = BehaviorTracer(
    workflow_id="your-workflow-id",
    api_endpoint="http://localhost:8000",
)

with tracer.trace_run() as run:
    with run.trace_step(step_index=0, tool_name="search") as step:
        result = search_tool(query)
        step.set_output(result)
        step.set_confidence(0.92)
    
    with run.trace_step(step_index=1, tool_name="respond") as step:
        response = generate_response(result)
        step.set_output(response)
        step.set_confidence(0.88)
```

## Configuration

All settings in `.env`:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://localhost/drift_detection` | PostgreSQL connection |
| `DRIFT_ALERT_THRESHOLD` | `0.65` | Composite score that triggers alerts |
| `STRUCTURAL_WEIGHT` | `0.35` | Weight of tool-sequence drift |
| `SEMANTIC_WEIGHT` | `0.40` | Weight of embedding-space drift |
| `DISTRIBUTIONAL_WEIGHT` | `0.25` | Weight of CUSUM/EWMA drift |
| `EWMA_ALPHA` | `0.3` | EWMA recency factor (higher = more reactive) |
| `CUSUM_THRESHOLD` | `5.0` | CUSUM detection threshold (sigma units) |
| `OPENAI_API_KEY` | *(empty)* | Optional: enables LLM drift explanations |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Local sentence-transformers model |

## Optional: LLM Drift Explanations

Set `OPENAI_API_KEY` in `.env` to enable GPT-4o generated explanations on alerts:

```
OPENAI_API_KEY=sk-...
```

Explanations are only generated when the composite drift score exceeds the alert threshold — LLM costs are gated behind real signal.

## Project Structure

```
behavioral-drift-detection/
├── api/                    # FastAPI control plane
│   ├── main.py             # App entry point, WebSocket manager
│   ├── models.py           # SQLAlchemy ORM models
│   ├── schemas.py          # Pydantic request/response schemas
│   ├── config.py           # Settings from environment
│   ├── database.py         # Async DB session management
│   └── routes/
│       ├── traces.py       # Trace ingestion & retrieval
│       ├── workflows.py    # Workflow CRUD + drift summary
│       ├── baselines.py    # Golden run baseline management
│       └── drift.py        # Drift score queries & time series
├── workers/
│   ├── drift_worker.py     # Main detection pipeline worker
│   ├── structural_analyzer.py  # Levenshtein tool-sequence diff
│   ├── semantic_analyzer.py    # Sentence-transformer embeddings
│   ├── distributional_analyzer.py  # CUSUM + EWMA
│   ├── signal_fusion.py    # Weighted composite score
│   ├── embeddings.py       # Embedding utilities
│   ├── explainability.py   # LLM explanation (on-alert only)
│   └── run_worker.py       # Worker entry point
├── sdk/
│   ├── behavior_trace.py   # BehaviorTracer SDK
│   └── otel_adapter.py     # OpenTelemetry span adapter
├── dashboard/              # React + Recharts frontend
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   └── api/
│   └── package.json
├── examples/
│   └── simulate_agent.py   # End-to-end simulation
├── tests/                  # Pytest suite
├── scripts/
│   └── init_db.py
├── docker-compose.yml
└── README.md
```