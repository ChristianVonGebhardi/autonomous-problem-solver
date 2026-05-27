# LicenseGuard — AI-Generated Code License Contamination Detection

LicenseGuard is a developer-native platform that detects open-source license contamination in AI-generated code before it reaches production. It analyzes code using MinHash fingerprinting, semantic embeddings, and a curated FOSS corpus to identify potentially problematic code and suggest remediations.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Developer Environment                                          │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │  Go CLI       │  │  VS Code Ext.  │  │  Pre-commit Hook │   │
│  │  (licenseguard│  │  (TypeScript)  │  │  (git hook)      │   │
│  └──────┬───────┘  └───────┬────────┘  └────────┬─────────┘   │
└─────────┼──────────────────┼───────────────────┼───────────────┘
          │                  │                   │
          ▼                  ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Backend (Python)                                       │
│  /api/v1/scan  /api/v1/remediate  /api/v1/dashboard/stats      │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │ MinHash LSH  │  │  Embeddings  │  │  License Classifier │    │
│  │ (datasketch) │  │(sentence-    │  │  (SPDX taxonomy)   │    │
│  └─────────────┘  │ transformers)│  └────────────────────┘    │
│                   └──────────────┘                             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
   │ PostgreSQL   │    │    Redis     │    │  React       │
   │ + pgvector   │    │  (RQ Queue)  │    │  Dashboard   │
   └─────────────┘    └──────────────┘    └──────────────┘
```

## Prerequisites

- **Docker** and **Docker Compose** v2+
- **Go 1.21+** (for CLI binary, optional)
- **Node.js 20+** (for dashboard development, optional)
- An **OpenAI API key** (optional, for AI-powered remediation suggestions)

## Quick Start

### 1. Clone and Configure

```bash
git clone <repo>
cd license-guard

# Copy environment file
cp .env.example .env

# (Optional) Add your OpenAI API key for AI remediation suggestions
echo "OPENAI_API_KEY=sk-..." >> .env
```

### 2. Start All Services

```bash
make up
```

This will start:
- **PostgreSQL** (port 5432) — with pgvector extension
- **Redis** (port 6379) — for job queuing
- **FastAPI Backend** (port 8000) — detection engine + REST API
- **RQ Worker** — async scan processor
- **RQ Dashboard** (port 9181) — job queue monitor
- **React Dashboard** (port 3000) — compliance UI

On first run, the backend will:
1. Run database migrations (Alembic)
2. Seed the FOSS corpus with representative code snippets
3. Download the `all-MiniLM-L6-v2` sentence-transformers model (~80MB)

> ⚠️ First startup takes 2-5 minutes to download the ML model.

### 3. Access the Services

| Service | URL |
|---------|-----|
| **Compliance Dashboard** | http://localhost:3000 |
| **API Documentation** | http://localhost:8000/docs |
| **API Health** | http://localhost:8000/api/v1/health |
| **Job Queue Monitor** | http://localhost:9181 |

## Usage

### Web Dashboard

Open http://localhost:3000 to access the compliance dashboard:

1. **Dashboard** — Overview of scan statistics, risk trends (7 days), top detected licenses
2. **Scan Code** — Paste code snippets and get instant license contamination analysis
3. **Scan History** — Browse all past scans with filtering by risk tier and status
4. **Corpus** — View the FOSS reference corpus statistics

### REST API

#### Synchronous Scan (immediate result)

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
  "scan_id": "uuid...",
  "status": "completed",
  "risk_tier": "high",
  "matches": [
    {
      "match_type": "near_duplicate",
      "similarity_score": 0.89,
      "license_spdx": "GPL-3.0-only",
      "license_risk_tier": "high",
      "source_repo": "python/cpython"
    }
  ],
  "recommendation": "BLOCK: This code matches a strong copyleft license..."
}
```

#### Async Scan (for large files)

```bash
# Submit
SCAN_ID=$(curl -s -X POST http://localhost:8000/api/v1/scan \
  -H "Content-Type: application/json" \
  -d '{"code": "...", "source": "ci_cd"}' | jq -r .scan_id)

# Poll result
curl http://localhost:8000/api/v1/scan/$SCAN_ID
```

#### Get Remediation Suggestion

```bash
curl -X POST http://localhost:8000/api/v1/remediate \
  -H "Content-Type: application/json" \
  -d '{"scan_id": "uuid..."}'
```

#### Dashboard Stats

```bash
curl http://localhost:8000/api/v1/dashboard/stats | python3 -m json.tool
```

### CLI Tool

#### Build

```bash
make build-cli
# Binary at: cli/bin/licenseguard
```

#### Install globally

```bash
make install-cli
```

#### Usage

```bash
# Check API status
licenseguard status

# Scan a file
licenseguard scan path/to/file.py

# Scan a directory
licenseguard scan ./src/

# Scan from stdin
cat myfile.py | licenseguard scan --stdin

# Scan staged changes (pre-commit)
licenseguard scan --staged

# Scan with JSON output
licenseguard scan myfile.py --output json

# Fail on medium or higher risk (for CI)
licenseguard scan ./src/ --fail-on medium

# Install as git pre-commit hook
licenseguard install-hook
```

#### Configure CLI

```bash
# Create config file
cp cli/.licenseguard.yaml.example ~/.licenseguard.yaml

# Or use environment variables
export LICENSEGUARD_API_URL=http://my-api.example.com
```

### CI/CD Integration

#### GitHub Actions

```yaml
name: License Contamination Check
on: [pull_request]

jobs:
  license-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install LicenseGuard CLI
        run: |
          curl -L https://releases.licenseguard.io/latest/licenseguard-linux-amd64 \
            -o /usr/local/bin/licenseguard
          chmod +x /usr/local/bin/licenseguard
      
      - name: Scan Changed Files
        env:
          LICENSEGUARD_API_URL: ${{ secrets.LICENSEGUARD_API_URL }}
        run: |
          git diff --name-only origin/main | \
            xargs -I {} licenseguard scan {} --fail-on high
```

#### Pre-commit Hook

```bash
# Install hook in any git repo
cd your-project
licenseguard install-hook

# Now every git commit will be scanned automatically
git add modified_file.py
git commit -m "Add feature"  # <- LicenseGuard scans here
```

## Detection Methods

| Method | Description | When Used |
|--------|-------------|-----------|
| **Exact Match** | SHA-256 hash of normalized code | Always |
| **MinHash LSH** | Jaccard similarity via shingling | Near-duplicate detection |
| **Semantic Embedding** | Cosine similarity via sentence-transformers | Semantic clones |

### Risk Tiers

| Tier | Description | Example Licenses | Action |
|------|-------------|-----------------|--------|
| 🔴 **HIGH** | Strong copyleft — may require open-sourcing your codebase | GPL-2.0, GPL-3.0, AGPL-3.0 | Block immediately |
| 🟡 **MEDIUM** | Weak copyleft — file/library level disclosure | LGPL, MPL-2.0, EPL-2.0 | Legal review |
| 🔵 **LOW** | Permissive — attribution required | MIT, Apache-2.0, BSD | Add attribution |
| 🟢 **CLEAN** | No contamination detected | — | Safe to use |

## Running Tests

```bash
# Backend tests
make test

# Or directly
docker compose exec backend pytest tests/ -v

# Individual test files
docker compose exec backend pytest tests/test_detector.py -v
docker compose exec backend pytest tests/test_scanner.py -v
```

## Running the Demo

```bash
make demo
```

This runs the end-to-end demo that:
1. Tests code tokenization and MinHash fingerprinting
2. Tests license taxonomy classification
3. Scans example GPL/MIT/clean code via the API
4. Shows detection results and risk tiers

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_SECRET_KEY` | `dev-secret-key` | JWT signing key |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `OPENAI_API_KEY` | *(empty)* | For AI remediation (optional) |
| `SIMILARITY_THRESHOLD` | `0.75` | Minimum similarity score to flag |
| `MINHASH_NUM_PERM` | `128` | MinHash permutations (higher = more accurate) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |

## Project Structure

```
license-guard/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── config.py          # Settings (pydantic-settings)
│   │   ├── models.py          # SQLAlchemy ORM models
│   │   ├── schemas.py         # Pydantic request/response schemas
│   │   ├── detector.py        # Core detection engine (MinHash, embeddings)
│   │   ├── scanner.py         # Scan job orchestrator
│   │   ├── remediation.py     # LLM-based remediation advisor
│   │   ├── license_taxonomy.py # SPDX risk tier classification
│   │   └── routes/            # FastAPI route handlers
│   │       ├── scan.py        # /scan, /remediate endpoints
│   │       ├── corpus.py      # /corpus endpoints
│   │       ├── dashboard.py   # /dashboard/stats
│   │       └── health.py      # /health
│   ├── alembic/               # Database migrations
│   ├── scripts/
│   │   ├── seed_corpus.py     # Seed FOSS corpus
│   │   └── demo.py            # End-to-end demo
│   └── tests/                 # pytest tests
├── cli/                        # Go CLI binary
│   ├── cmd/licenseguard/      # CLI entry point
│   └── internal/commands/     # Cobra commands
│       ├── scan.go            # scan command
│       ├── hook.go            # install-hook/remove-hook
│       ├── status.go          # status command
│       └── version.go         # version command
├── dashboard/                  # React/TypeScript dashboard
│   └── src/
│       ├── pages/             # Dashboard, Scan, History, Corpus pages
│       ├── components/        # Reusable UI components
│       └── api/               # API client
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Resetting

```bash
# Full reset (wipes database)
make reset

# Just stop services
make down

# View logs
make logs
```

## Air-Gapped / Enterprise Deployment

For enterprises with strict data policies, all services can run locally:

1. The ML model (`all-MiniLM-L6-v2`) is cached in a Docker volume
2. No external API calls are made unless `OPENAI_API_KEY` is set
3. The corpus is self-hosted in PostgreSQL

To deploy on Kubernetes, see the `docker-compose.yml` as a reference for service definitions and environment variables. A Helm chart can be derived from the Compose file.

## Known Limitations (MVP)

- The FOSS corpus contains ~11 representative snippets (production would have millions from GitHub BigQuery)
- The MinHash comparison is O(n) against the corpus (production uses LSH indexing for O(1) lookup)
- Vector search falls back to manual cosine similarity if pgvector is unavailable
- Remediation suggestions require an OpenAI API key; without one, template-based guidance is provided