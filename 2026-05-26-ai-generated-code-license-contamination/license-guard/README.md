# LicenseGuard - AI-Generated Code License Contamination Detection

## Overview

LicenseGuard is a developer-native license contamination detection platform that intercepts AI-generated code at multiple pipeline stages. It detects potential open-source license contamination in AI-generated code using AST parsing, MinHash LSH fingerprinting, and semantic similarity analysis.

## Architecture

- **Backend**: Python/FastAPI with PostgreSQL (pgvector), Redis, and RQ workers
- **CLI**: Go binary for pre-commit hooks
- **Dashboard**: React/TypeScript compliance dashboard
- **Detection**: tree-sitter AST parsing + MinHash LSH + sentence-transformers

## Prerequisites

- Docker and Docker Compose
- Go 1.21+ (for CLI)
- Node.js 18+ (for dashboard)
- Python 3.11+ (for backend, if running without Docker)
- OpenAI API key (for remediation suggestions)

## Quick Start (Docker Compose)

```bash
cd license-guard

# Copy environment config
cp .env.example .env

# Add your OpenAI API key to .env
# OPENAI_API_KEY=sk-...

# Start all services
docker-compose up --build

# In another terminal, seed the corpus with sample FOSS snippets
docker-compose exec backend python scripts/seed_corpus.py

# Access the dashboard
open http://localhost:3000

# API is available at
open http://localhost:8000/docs
```

## Services

| Service | URL | Description |
|---------|-----|-------------|
| FastAPI Backend | http://localhost:8000 | REST API + Swagger docs |
| React Dashboard | http://localhost:3000 | Compliance dashboard |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Job queue |
| RQ Dashboard | http://localhost:9181 | Job monitoring |

## CLI (Pre-commit Hook)

### Install CLI

```bash
cd cli
go build -o licenseguard-cli ./cmd/licenseguard
sudo mv licenseguard-cli /usr/local/bin/

# Or use the install script
./install-hook.sh
```

### Manual Scan

```bash
# Scan a file
licenseguard-cli scan --file path/to/file.py --api-url http://localhost:8000

# Scan git diff (pre-commit mode)
licenseguard-cli scan --diff --api-url http://localhost:8000

# Scan with output format
licenseguard-cli scan --file path/to/file.py --format json
```

### Install as Pre-commit Hook

```bash
# In your project repository
licenseguard-cli install-hook --api-url http://localhost:8000
```

## API Usage

### Scan a Code Snippet

```bash
curl -X POST http://localhost:8000/api/v1/scan \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def binary_search(arr, target):\n    left, right = 0, len(arr) - 1\n    while left <= right:\n        mid = (left + right) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1",
    "language": "python",
    "source": "ai_assistant",
    "filename": "search.py"
  }'
```

### Get Scan Results

```bash
curl http://localhost:8000/api/v1/scan/{scan_id}
```

### Get Remediation Suggestion

```bash
curl -X POST http://localhost:8000/api/v1/remediate \
  -H "Content-Type: application/json" \
  -d '{"scan_id": "...", "snippet_id": "..."}'
```

## Running Tests

```bash
# Backend tests
cd backend
pip install -r requirements.txt
pytest tests/ -v

# CLI tests
cd cli
go test ./...
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | - | OpenAI API key for remediation |
| `DATABASE_URL` | postgresql://... | PostgreSQL connection string |
| `REDIS_URL` | redis://localhost:6379 | Redis connection string |
| `SIMILARITY_THRESHOLD` | 0.8 | Match threshold (0-1) |
| `API_SECRET_KEY` | - | JWT secret for API auth |

## License Risk Tiers

| Tier | Licenses | Action |
|------|----------|--------|
| 🔴 HIGH | GPL-2.0, GPL-3.0, AGPL-3.0 | Block commit |
| 🟡 MEDIUM | LGPL-2.1, MPL-2.0, EUPL | Warn developer |
| 🟢 LOW | MIT, Apache-2.0, BSD | Informational |
| ⬜ UNKNOWN | Unidentified | Review required |