# LLM Prompt Regression Monitor

A continuous quality-monitoring platform for LLM-powered applications. It intercepts production inference calls, scores outputs semantically, and statistically detects silent quality regressions before users notice.

## Overview

```
Client App → Proxy (port 8000) → LLM Provider (OpenAI/Anthropic)
                ↓
          Redis Queue
                ↓
         Celery Worker → Quality Scorer → PostgreSQL + pgvector
                                              ↓
                                      Drift Detector (CUSUM + Mann-Whitney)
                                              ↓
                                      Alert Router (Slack/PagerDuty)
                                              ↓
                                      Dashboard (port 3000)
```

## Prerequisites

- Docker & Docker Compose v2+
- (Optional) OpenAI API key for LLM-as-judge scoring and embedding similarity

## Setup

### 1. Clone and configure

```bash
git clone <repo>
cd prompt-regression-monitor

# Copy and edit environment file
cp .env.example .env
```

Edit `.env`:

```env
# Required for LLM-as-judge scoring and embedding similarity
OPENAI_API_KEY=sk-...

# Optional: alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
PAGERDUTY_ROUTING_KEY=...

# LLM provider to proxy to (default: OpenAI)
LLM_PROVIDER_BASE_URL=https://api.openai.com
JUDGE_MODEL=gpt-4o-mini
```

### 2. Start the stack

```bash
docker compose up --build
```

Services that start:
| Service | Port | Purpose |
|---------|------|---------|
| `proxy` | 8000 | OpenAI-compatible proxy interceptor |
| `api` | 8001 | Dashboard REST API |
| `worker` | — | Celery quality scoring workers |
| `beat` | — | Celery periodic scheduler |
| `postgres` | 5432 | Database + pgvector |
| `redis` | 6379 | Task queue |
| `dashboard` | 3000 | React dashboard |

### 3. Open the dashboard

Visit **http://localhost:3000**

## Integration

### Point your OpenAI SDK at the proxy

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-openai-key",       # passed through to OpenAI
    base_url="http://localhost:8000/v1",  # proxy endpoint
)

# Tag requests with a template name for grouping
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}],
    extra_headers={"X-Prompt-Template": "my-chatbot-v1"},
)
```

```javascript
// Node.js
import OpenAI from 'openai';
const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  baseURL: 'http://localhost:8000/v1',
  defaultHeaders: { 'X-Prompt-Template': 'my-chatbot-v1' },
});
```

### Curl example

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "X-Prompt-Template: my-template" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "What is 2+2?"}]
  }'
```

## Adding Golden References

Golden references are known-good input/output pairs used to score new outputs.

**Via the dashboard:** Go to Templates → select your template → Add Reference.

**Via API:**
```bash
# First create a template
curl -X POST http://localhost:8001/api/templates \
  -H "Content-Type: application/json" \
  -d '{"name": "my-chatbot-v1", "description": "Customer support bot"}'

# Add a golden reference
curl -X POST http://localhost:8001/api/golden-references \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "<template-id-from-above>",
    "input_messages": [{"role": "user", "content": "What is your return policy?"}],
    "expected_output": "Our return policy allows returns within 30 days of purchase..."
  }'
```

## Testing the Detection Pipeline (No API Key Required)

Use the built-in regression simulator:

```bash
# Inject synthetic scores with 30% quality degradation
curl -X POST "http://localhost:8001/api/simulate/regression?template_name=test&metric_degradation=0.3"

# Or use the Simulate tab in the dashboard
```

This injects:
- 30 baseline samples (24h–4h ago) with ~0.85 quality score
- 15 degraded samples (last 4h) with ~0.595 quality score
- Triggers CUSUM + Mann-Whitney detection immediately

Alerts will appear in the **Alerts** panel within seconds.

## Quality Metrics

| Metric | Description | Range |
|--------|-------------|-------|
| `judge_overall` | LLM-as-judge overall quality | 0–1 |
| `judge_relevance` | LLM-as-judge relevance | 0–1 |
| `judge_accuracy` | LLM-as-judge factual accuracy | 0–1 |
| `judge_coherence` | LLM-as-judge coherence | 0–1 |
| `judge_completeness` | LLM-as-judge completeness | 0–1 |
| `judge_safety` | LLM-as-judge safety check | 0–1 |
| `embedding_max_similarity` | Max cosine sim vs golden refs | 0–1 |
| `embedding_mean_similarity` | Mean cosine sim vs golden refs | 0–1 |
| `rouge1_fmeasure` | ROUGE-1 F-measure vs golden refs | 0–1 |
| `rouge2_fmeasure` | ROUGE-2 F-measure vs golden refs | 0–1 |
| `rougeL_fmeasure` | ROUGE-L F-measure vs golden refs | 0–1 |
| `format_nonempty` | Response is not empty | 0/1 |
| `format_length_adequacy` | Response has adequate length | 0–1 |
| `format_repetition_score` | Low repetition | 0–1 |
| `safety_no_pii` | No PII detected | 0/1 |
| `behavior_no_refusal` | No unexpected refusals | 0/1 |

## Drift Detection

Two detectors run in parallel per metric per template:

**CUSUM (Cumulative Sum Control Chart)**
- Sequential change-point detection
- Configurable slack (`CUSUM_SLACK`) and threshold (`CUSUM_THRESHOLD`)
- Detects sustained downward shifts in quality mean

**Mann-Whitney U Test**
- Non-parametric test comparing baseline vs recent distributions
- Significance level configurable (`MANN_WHITNEY_ALPHA=0.05`)
- Robust to non-normal score distributions

Alert is fired when **either** detector triggers AND the current mean is ≥5% below baseline. Severity levels:
- **Warning**: 5–15% degradation
- **Error**: 15–30% degradation  
- **Critical**: >30% degradation

## Alert Destinations

### Slack
```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
```

### PagerDuty
```env
PAGERDUTY_ROUTING_KEY=your-events-api-v2-key
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard/summary` | GET | KPI summary |
| `/api/templates` | GET/POST | List/create templates |
| `/api/golden-references` | GET/POST | List/create golden refs |
| `/api/metrics/time-series` | GET | Metric time-series |
| `/api/metrics/latest` | GET | Latest metric averages |
| `/api/alerts` | GET | List drift alerts |
| `/api/alerts/:id/acknowledge` | POST | Acknowledge alert |
| `/api/inference-logs` | GET | List inference logs |
| `/api/inference-logs/:id` | GET | Get log with scores |
| `/api/simulate/regression` | POST | Inject synthetic regression |
| `/api/trigger/drift-detection` | POST | Manually trigger detection |

## Configuration

All settings can be set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI key (for judge + embeddings) |
| `LLM_PROVIDER_BASE_URL` | `https://api.openai.com` | Upstream LLM provider |
| `JUDGE_MODEL` | `gpt-4o-mini` | Model for LLM-as-judge |
| `CUSUM_THRESHOLD` | `5.0` | CUSUM control limit (× σ) |
| `CUSUM_SLACK` | `0.5` | CUSUM allowance parameter |
| `MANN_WHITNEY_ALPHA` | `0.05` | MW significance level |
| `MIN_SAMPLES_FOR_DETECTION` | `10` | Min baseline samples needed |
| `BASELINE_WINDOW_HOURS` | `24` | Baseline lookback window |
| `DETECTION_WINDOW_HOURS` | `4` | Recent window for comparison |
| `USE_LLM_JUDGE` | `true` | Enable LLM-as-judge scoring |
| `USE_EMBEDDINGS` | `true` | Enable embedding similarity |
| `USE_ROUGE` | `true` | Enable ROUGE metrics |

## Development

```bash
# Run backend only (with local postgres + redis)
cd backend
pip install -r requirements.txt
uvicorn app.proxy:app --port 8000 --reload &
uvicorn app.api:app --port 8001 --reload &
celery -A app.worker worker --loglevel=info

# Run dashboard
cd dashboard
npm install
npm start
```

## Architecture

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full system design.

The key design decisions:
1. **Proxy is zero-trust for the hot path** — scoring failures never surface to the client
2. **Statistical process control** — CUSUM detects trends; Mann-Whitney detects distributional shifts
3. **Configurable evaluator suite** — teams can start with format checks only (no API key) and add LLM-as-judge later
4. **Single datastore** — PostgreSQL + pgvector eliminates a separate vector DB

## Troubleshooting

**Dashboard shows "API Offline"**  
→ Make sure `docker compose up` is running and `api` service on port 8001 is healthy.

**No scores appearing for inferences**  
→ Check Celery worker logs: `docker compose logs worker`

**Alerts not firing**  
→ Need ≥10 baseline samples. Use the Simulate panel to inject synthetic data.

**LLM judge scores missing**  
→ `OPENAI_API_KEY` is not set. Format and rule-based metrics still work without it.