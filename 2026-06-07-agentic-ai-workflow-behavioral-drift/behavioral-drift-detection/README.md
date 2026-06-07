# Behavioral Drift Detection Platform

An agentic AI workflow behavioral drift detection platform that monitors multi-step agent pipelines for silent deviations in tool selection, reasoning, and output distributions — even when infrastructure metrics remain green.

## Architecture (MVP)

```
Agent Runtime
    ↓ (BehaviorTrace SDK — OTEL-compatible spans)
SQLite Event Queue (Kafka-replaceable)
    ↓
Drift Detection Workers:
  - Structural Analyzer (tool sequence / step order)
  - Semantic Analyzer (cosine distance from baseline embeddings)
  - Distributional Analyzer (CUSUM / EWMA on output distributions)
    ↓
Signal Fusion → Unified Drift Score
    ↓
TimescaleDB (or PostgreSQL) → FastAPI → React Dashboard
```

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- PostgreSQL 14+ with TimescaleDB extension **OR** use the included SQLite fallback for local dev
- (Optional) OpenAI API key for LLM-powered drift explanations

## Quick Start (Local Dev with SQLite + PostgreSQL)

### 1. Clone and set up Python environment

```bash
cd behavioral-drift-detection
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL
```

For local dev without TimescaleDB:
```
DATABASE_URL=postgresql://localhost/drift_detection
```

### 3. Initialize the database

```bash
python -m scripts.init_db
```

### 4. Start the API server

```bash
uvicorn api.main:app --reload --port 8000
```

### 5. Start the drift detection worker

```bash
python -m workers.drift_worker
```

### 6. Start the React dashboard

```bash
cd dashboard
npm install
npm run dev
```

Dashboard available at http://localhost:5173

API docs at http://localhost:8000/docs

### 7. Run the example agent simulation

```bash
python -m examples.simulate_agent
```

This sends a series of agent traces (including injected drift) and you can watch the dashboard update in real time.

## Running Tests

```bash
pytest tests/ -v
```

## Using the SDK in Your Agent

```python
from sdk.behavior_trace import BehaviorTracer

tracer = BehaviorTracer(
    workflow_id="my-workflow",
    api_endpoint="http://localhost:8000"
)

with tracer.trace_run() as run:
    with run.trace_step(step_index=0, tool_name="search") as step:
        result = my_search_tool(query)
        step.set_output(result)
        step.set_confidence(0.92)
    
    with run.trace_step(step_index=1, tool_name="summarize") as step:
        summary = my_summarize_tool(result)
        step.set_output(summary)
```

## Key Concepts

- **Golden Runs**: Manually approved traces that establish the behavioral baseline
- **Structural Drift**: Changes in tool selection order or step sequencing
- **Semantic Drift**: Embedding-space distance of reasoning from baseline intent
- **Distributional Drift**: CUSUM/EWMA detection of output distribution shifts
- **Unified Drift Score**: Weighted composite (0–1) across all three signal layers

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | required | PostgreSQL connection string |
| `OPENAI_API_KEY` | optional | Enables LLM drift explanations |
| `DRIFT_ALERT_THRESHOLD` | `0.65` | Composite score that triggers alerts |
| `STRUCTURAL_WEIGHT` | `0.35` | Weight for structural signal |
| `SEMANTIC_WEIGHT` | `0.40` | Weight for semantic signal |
| `DISTRIBUTIONAL_WEIGHT` | `0.25` | Weight for distributional signal |
| `EWMA_ALPHA` | `0.3` | EWMA smoothing factor |
| `CUSUM_THRESHOLD` | `5.0` | CUSUM detection threshold |
| `WORKER_POLL_INTERVAL` | `2` | Worker polling interval (seconds) |