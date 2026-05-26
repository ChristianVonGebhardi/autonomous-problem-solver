# LicenseGuard

**AI-Generated Code License Contamination Detection Platform**

LicenseGuard automatically scans code for open-source license contamination — detecting when AI coding assistants (GitHub Copilot, Cursor, Claude) reproduce copyrighted FOSS code in your codebase. It uses MinHash fingerprinting, semantic embeddings, and a FOSS corpus to identify GPL, AGPL, LGPL, and other copyleft code before it reaches production.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Developer Tools                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Go CLI       │  │  Pre-commit  │  │  React        │  │
│  │  licenseguard │  │  Hook        │  │  Dashboard    │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘  │
└─────────┼────────────────┼──────────────────┼───────────┘
          │                │                  │
          ▼                ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Backend (Python)                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  /scan   │  │/remediate│  │/dashboard│              │
│  └────┬─────┘  └────┬─────┘  └──────────┘              │
│       │             │                                   │
│  ┌────▼──────────────▼─────────────────────────────┐   │
│  │  Detection Engine                                │   │
│  │  MinHash LSH + Sentence Transformers + pgvector  │   │
│  └────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
          │                │
          ▼                ▼
    PostgreSQL          Redis
    (embeddings,        (job queue)
     audit trail)
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Go 1.21+ (for CLI)
- Node.js 20+ (for dashboard development)

### 1. Start the Backend

```bash
cd license-guard

# Copy environment config
cp .env.example .env
# Optionally add your OpenAI key for AI-powered remediation:
# OPENAI_API_KEY=sk-...

# Start all services
docker compose up -d

# Check status
docker compose ps
```

Services started:
- **Backend API**: http://localhost:8000
- **Dashboard**: http://localhost:3000
- **RQ Dashboard** (job monitoring): http://localhost:9181
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### 2. Seed the FOSS Corpus

```bash
# Wait for backend to be healthy, then seed the corpus
docker compose exec backend python scripts/seed_corpus.py
```

This seeds the corpus with ~11 representative FOSS snippets covering GPL-2.0, GPL-3.0, AGPL-3.0, LGPL-2.1, MPL-2.0, MIT, Apache-2.0, BSD-3-Clause, and PSF licenses.

### 3. Verify Everything Works

```bash
# Check API health
curl http://localhost:8000/api/v1/health

# Check corpus stats  
curl http://localhost:8000/api/v1/corpus/stats
```

---

## Using the Dashboard

Open http://localhost:3000 in your browser.

**Dashboard** — compliance overview with risk trends, top detected licenses, recent scans

**Scan Code** — paste AI-generated code to check for license contamination. Includes example snippets:
- "GPL heapsort (python)" — triggers a high-risk GPL match
- "MIT debounce (javascript)" — triggers a low-risk MIT match
- "Clean code (python)" — returns clean result

**Scan History** — browse all scans with filtering by risk tier and status

**Corpus** — view the FOSS corpus statistics and license breakdown

---

## Using the API

### Scan code synchronously

```bash
curl -X POST http://localhost:8000/api/v1/scan/sync \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def heappush(heap, item):\n    heap.append(item)\n    _siftdown(heap, 0, len(heap)-1)",
    "language": "python",
    "source": "api"
  }'
```

Response:
```json
{
  "scan_id": "abc123...",
  "status": "completed",
  "risk_tier": "high",
  "matches": [{
    "match_type": "semantic",
    "similarity_score": 0.89,
    "license_spdx": "GPL-3.0-only",
    "license_risk_tier": "high",
    "source_repo": "python/cpython"
  }],
  "recommendation": "BLOCK: This code matches a strong copyleft license...",
  "message": "Scan completed. Found 1 potential license matches."
}
```

### Asynchronous scan (for large files)

```bash
# Submit
curl -X POST http://localhost:8000/api/v1/scan \
  -H "Content-Type: application/json" \
  -d '{"code": "...", "source": "ci_cd"}'

# Poll for result
curl http://localhost:8000/api/v1/scan/{scan_id}
```

### Request remediation suggestion

```bash
curl -X POST http://localhost:8000/api/v1/remediate \
  -H "Content-Type: application/json" \
  -d '{"scan_id": "abc123..."}'
```

### API Documentation

Interactive docs available at http://localhost:8000/docs

---

## Using the CLI

### Build

```bash
cd license-guard/cli
go build -o bin/licenseguard ./cmd/licenseguard/
```

### Install globally

```bash
cd license-guard/cli
go install ./cmd/licenseguard/
```

### Commands

```bash
# Check API status
licenseguard status

# Scan a file
licenseguard scan myfile.py

# Scan a directory
licenseguard scan ./src/

# Scan from stdin
cat myfile.py | licenseguard scan --stdin

# Scan git staged changes
licenseguard scan --staged

# JSON output (for CI/CD integration)
licenseguard scan --output json myfile.py

# Fail on medium+ risk (default: high)
licenseguard scan --fail-on medium myfile.py

# Install pre-commit hook
licenseguard install-hook

# Remove pre-commit hook
licenseguard remove-hook
```

### Configuration

Create `~/.licenseguard.yaml`:

```yaml
api_url: http://localhost:8000
verbose: false
```

Or use environment variables:
```bash
export LICENSEGUARD_API_URL=https://your-api.company.com
export LICENSEGUARD_VERBOSE=true
```

### Pre-commit Hook

```bash
cd your-repo
licenseguard install-hook
```

The hook scans all staged files before each commit. If high-risk contamination is found, the commit is blocked.

To bypass (not recommended):
```bash
git commit --no-verify
```

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/license-check.yml
name: License Contamination Check

on: [pull_request]

jobs:
  license-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install LicenseGuard CLI
        run: |
          go install github.com/licenseguard/cli/cmd/licenseguard@latest
      
      - name: Scan changed files
        env:
          LICENSEGUARD_API_URL: ${{ secrets.LICENSEGUARD_API_URL }}
        run: |
          git diff --name-only origin/main...HEAD | \
            xargs licenseguard scan --fail-on high --output json
```

---

## Detection Methods

LicenseGuard uses three complementary detection strategies:

| Method | How it works | Best for |
|--------|-------------|----------|
| **Exact Match** | SHA256 hash of normalized code | Verbatim copies |
| **MinHash LSH** | Jaccard similarity on token k-grams | Near-duplicate code with minor edits |
| **Semantic Embedding** | Cosine similarity of code embeddings (sentence-transformers) | Algorithmic clones, paraphrased implementations |

### Risk Tier Taxonomy

| Tier | Examples | Action |
|------|----------|--------|
| 🔴 **High** | GPL-2.0, GPL-3.0, AGPL-3.0, SSPL | Block — requires source disclosure |
| 🟡 **Medium** | LGPL-2.1, MPL-2.0, EPL-2.0 | Warn — file-level copyleft may apply |
| 🔵 **Low** | MIT, Apache-2.0, BSD-3-Clause | Info — attribution required |
| ✅ **Clean** | No matches | Safe to use |

---

## Development

### Backend Development

```bash
cd license-guard/backend

# Install dependencies
pip install -r requirements.txt

# Set up local database
docker compose up postgres redis -d

# Run migrations
python -m alembic upgrade head

# Seed corpus
python scripts/seed_corpus.py

# Start API
uvicorn app.main:app --reload --port 8000

# Start worker
python -m rq worker --url redis://localhost:6379/0 scans
```

### Run Tests

```bash
cd license-guard/backend
pytest tests/ -v
```

### Dashboard Development

```bash
cd license-guard/dashboard
npm install
npm run dev
# → http://localhost:3000
```

### CLI Development

```bash
cd license-guard/cli
go run ./cmd/licenseguard/ --help
go test ./...
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://licenseguard:licenseguard@localhost:5432/licenseguard` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `OPENAI_API_KEY` | (empty) | OpenAI key for AI remediation (optional) |
| `SIMILARITY_THRESHOLD` | `0.75` | Minimum similarity score to flag (0-1) |
| `MINHASH_NUM_PERM` | `128` | MinHash permutations (higher = more accurate) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |

---

## Production Deployment

For production, use the Docker Compose setup with your own secrets:

```bash
# Generate a strong API key
API_SECRET_KEY=$(openssl rand -hex 32)

# Set production environment
export DATABASE_URL=postgresql://user:pass@your-db-host:5432/licenseguard
export REDIS_URL=redis://your-redis-host:6379/0
export OPENAI_API_KEY=sk-your-key
export API_SECRET_KEY=$API_SECRET_KEY

docker compose up -d
```

For Kubernetes/EKS deployment, see the architecture docs.

---

## License

This project is proprietary software. The corpus snippets used for detection retain their original licenses (GPL, MIT, Apache, etc.) and are used for fingerprinting purposes only — not included in any distributed binary.