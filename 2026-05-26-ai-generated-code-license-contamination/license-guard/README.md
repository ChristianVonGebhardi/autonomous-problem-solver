# LicenseGuard

**AI-Generated Code License Contamination Detection Platform**

LicenseGuard scans AI-generated code (from GitHub Copilot, Cursor, Claude, ChatGPT, etc.) for open-source license contamination before it reaches production. It uses MinHash LSH fingerprinting and semantic embeddings to detect near-duplicate and semantically similar code from known FOSS repositories.

## Architecture

```
Developer → IDE / Pre-commit Hook / CI/CD
                    ↓
           LicenseGuard API (FastAPI)
                    ↓
    AST Tokenization + MinHash + Embeddings
                    ↓
          FOSS Corpus Comparison (pgvector)
                    ↓
    License Risk Classification (SPDX tiers)
                    ↓
        Remediation Suggestions (OpenAI)
                    ↓
         Compliance Dashboard (React)
```

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Go 1.21+ (for CLI binary)
- Node.js 20+ (optional, for dashboard dev)

### 1. Clone and Configure

```bash
git clone <repo>
cd license-guard
cp .env.example .env
# Edit .env if needed (optional: add OPENAI_API_KEY for AI remediation)
```

### 2. Start All Services

```bash
make up
```

This starts:
- **PostgreSQL** (with pgvector) on port 5432
- **Redis** on port 6379
- **FastAPI Backend** on port 8000
- **RQ Worker** (async scan jobs)
- **RQ Dashboard** on port 9181
- **React Dashboard** on port 3000

Seeds the corpus with sample FOSS snippets automatically.

### 3. Access the Dashboard

Open [http://localhost:3000](http://localhost:3000)

- **Dashboard**: Compliance overview, risk trends
- **Scan Code**: Paste AI-generated code for instant scanning
- **Scan History**: Browse past scans with filtering
- **Corpus**: View the FOSS snippet database

### 4. API Documentation

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive Swagger UI.

---

## CLI Usage

### Build the CLI

```bash
make build-cli
# Binary: cli/bin/licenseguard
```

Or install globally:
```bash
make install-cli
```

### Scan a File

```bash
licenseguard scan myfile.py
```

### Scan from stdin (git diff)

```bash
git diff HEAD | licenseguard scan --stdin
```

### Scan Staged Changes (pre-commit)

```bash
licenseguard scan --staged
```

### Install Pre-commit Hook

```bash
cd your-project
licenseguard install-hook
```

This installs a git pre-commit hook that automatically scans staged files before each commit.

### Check API Status

```bash
licenseguard status
```

### CLI Options

```bash
licenseguard scan [file] \
  --language python \      # Language hint
  --output json \          # Output format: text|json
  --fail-on high \         # Exit code 1 if risk >= this tier
  --staged \               # Scan git staged files
  --stdin                  # Read from stdin
```

---

## API Usage

### Synchronous Scan (blocks until complete)

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
  "scan_id": "uuid",
  "status": "completed",
  "risk_tier": "high",
  "matches": [
    {
      "match_type": "near_duplicate",
      "similarity_score": 0.87,
      "license_spdx": "GPL-3.0-only",
      "license_risk_tier": "high",
      "source_repo": "python/cpython"
    }
  ],
  "recommendation": "BLOCK: This code matches a strong copyleft license..."
}
```

### Async Scan (returns job ID)

```bash
# Submit
curl -X POST http://localhost:8000/api/v1/scan \
  -H "Content-Type: application/json" \
  -d '{"code": "...", "source": "ci_cd"}'

# Poll
curl http://localhost:8000/api/v1/scan/{scan_id}
```

### Request Remediation

```bash
curl -X POST http://localhost:8000/api/v1/remediate \
  -H "Content-Type: application/json" \
  -d '{"scan_id": "uuid"}'
```

### List Scans

```bash
curl "http://localhost:8000/api/v1/scans?risk_tier=high&limit=20"
```

---

## Risk Tier Taxonomy

| Tier | Licenses | Action |
|------|----------|--------|
| 🔴 **HIGH** | GPL-2/3, AGPL-3, SSPL | Block — may require full source disclosure |
| 🟡 **MEDIUM** | LGPL, MPL, EPL | Warn — file-level or library copyleft |
| 🔵 **LOW** | MIT, Apache-2.0, BSD | Info — attribution required |
| ✅ **CLEAN** | — | No contamination detected |

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/license-check.yml
name: License Contamination Check

on: [pull_request]

jobs:
  license-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install LicenseGuard CLI
        run: |
          curl -L https://github.com/your-org/licenseguard/releases/latest/download/licenseguard-linux-amd64 \
            -o /usr/local/bin/licenseguard
          chmod +x /usr/local/bin/licenseguard
      
      - name: Scan changed files
        env:
          LICENSEGUARD_API_URL: ${{ secrets.LICENSEGUARD_API_URL }}
        run: |
          git diff --name-only origin/main...HEAD | \
            xargs licenseguard scan --fail-on high --output json
```

### GitLab CI

```yaml
license-scan:
  stage: test
  script:
    - licenseguard scan --staged --fail-on high
  allow_failure: false
```

---

## Development

### Backend Only (without Docker)

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL and Redis (or use docker)
docker compose up postgres redis -d

# Run migrations
python -m alembic upgrade head

# Seed corpus
python scripts/seed_corpus.py

# Start API
uvicorn app.main:app --reload

# Start worker (separate terminal)
python -m rq worker --url redis://localhost:6379/0 scans
```

### Dashboard Development

```bash
cd dashboard
npm install
npm run dev
# Opens at http://localhost:5173
```

### Run Demo

```bash
# With Docker running:
make demo
# or
docker compose exec backend python scripts/demo.py
```

### Run Tests

```bash
make test
# or
docker compose exec backend pytest tests/ -v
```

### CLI Development

```bash
cd cli
go mod tidy
go run ./cmd/licenseguard/ version
go run ./cmd/licenseguard/ status
```

---

## Configuration

Edit `.env`:

```env
# Required for AI-powered remediation suggestions
OPENAI_API_KEY=sk-...

# Detection sensitivity (0.0-1.0, lower = more matches)
SIMILARITY_THRESHOLD=0.75

# MinHash permutations (higher = more accurate, slower)
MINHASH_NUM_PERM=128

# Sentence transformer model
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

---

## Project Structure

```
license-guard/
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── main.py          # FastAPI app
│   │   ├── config.py        # Settings (pydantic)
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── schemas.py       # Pydantic schemas
│   │   ├── detector.py      # Core detection engine
│   │   ├── scanner.py       # Scan job orchestrator
│   │   ├── remediation.py   # LLM remediation advisor
│   │   ├── license_taxonomy.py  # SPDX risk tiers
│   │   └── routes/          # API route handlers
│   ├── alembic/             # DB migrations
│   ├── scripts/             # Seed + demo scripts
│   └── tests/               # pytest test suite
├── cli/                     # Go CLI binary
│   ├── cmd/licenseguard/    # Entry point
│   └── internal/commands/   # Cobra commands
├── dashboard/               # React + Tailwind UI
│   └── src/
│       ├── pages/           # Dashboard, Scan, History, Corpus
│       ├── components/      # Layout, RiskBadge, StatCard
│       └── api/             # API client
├── docker-compose.yml
├── Makefile
└── .env.example
```

---

## How Detection Works

1. **Tokenization**: Code is tokenized using regex-based AST normalization (tree-sitter optional)
2. **MinHash LSH**: Tokens are shingled into trigrams and fingerprinted for near-duplicate detection
3. **Semantic Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` encodes code semantically
4. **Corpus Comparison**:
   - Exact hash match (normalized whitespace/case)
   - MinHash Jaccard similarity against corpus
   - pgvector cosine similarity on embeddings
5. **License Classification**: Matched snippets mapped to SPDX identifiers → risk tiers
6. **Remediation**: OpenAI GPT-4o-mini suggests license-compatible rewrites

---

## License

MIT — see [LICENSE](LICENSE)