# GuardRail — AI-Hallucinated Package Dependency Interception

GuardRail is a multi-layer supply-chain interception platform that validates AI-generated package dependencies at three enforcement points:
1. **CLI Scanner** — scan manifest files before committing
2. **Package Manager Shims** — intercept `pip install` / `npm install` before execution
3. **CI/CD Gate** — GitHub Actions integration for PR/push validation
4. **Policy Server** — centralized allow/block lists and risk thresholds

## Architecture

```
guardrail/
├── core/               # Core validation engine (Python)
│   ├── validator.py    # Orchestrates all checks
│   ├── registry.py     # Live registry existence checks
│   ├── heuristics.py   # Slopsquatting heuristic scoring
│   ├── reputation.py   # Package reputation scoring
│   └── cache.py        # SQLite cache (15-min TTL)
├── cli/                # CLI tool (guardrail scan)
│   └── main.py
├── shims/              # Package manager shim wrappers
│   ├── pip_shim.py
│   └── npm_shim.py
├── policy_server/      # Go policy server
│   ├── main.go
│   ├── go.mod
│   └── go.sum
├── vscode_extension/   # VS Code extension skeleton
│   ├── package.json
│   └── src/extension.ts
├── github_action/      # GitHub Actions action definition
│   └── action.yml
├── tests/              # Test suite
│   └── test_validator.py
├── requirements.txt
└── setup.py
```

## Quick Start

### Prerequisites
- Python 3.9+
- pip
- (Optional) Go 1.21+ for policy server
- (Optional) Node.js 18+ for VS Code extension

### Installation

```bash
# Clone the repo
git clone https://github.com/your-org/guardrail
cd guardrail

# Install Python dependencies
pip install -r requirements.txt

# Install GuardRail CLI
pip install -e .
```

### Basic Usage

#### Scan a manifest file
```bash
# Scan requirements.txt
guardrail scan requirements.txt

# Scan package.json
guardrail scan package.json

# Scan with JSON output
guardrail scan requirements.txt --format json

# Scan with strict mode (exit 1 on any warning)
guardrail scan requirements.txt --strict

# Scan with policy server
guardrail scan requirements.txt --policy-server http://localhost:8080
```

#### Scan a single package name
```bash
guardrail check numpy --ecosystem pypi
guardrail check react --ecosystem npm
guardrail check lodahs --ecosystem npm   # typosquat of lodash
```

#### Install shims (intercept pip/npm)
```bash
# Install pip shim
guardrail install-shim pip

# Install npm shim  
guardrail install-shim npm

# Now any pip install will be intercepted:
pip install some-ai-hallucinated-package  # → blocked with warning
```

### Policy Server

```bash
# Start policy server (default port 8080)
cd policy_server
go run main.go

# Or with Docker
docker build -t guardrail-policy .
docker run -p 8080:8080 guardrail-policy

# Add to allow list
curl -X POST http://localhost:8080/api/v1/allowlist \
  -H "Content-Type: application/json" \
  -d '{"package": "my-internal-pkg", "ecosystem": "pypi"}'

# Set risk threshold
curl -X PUT http://localhost:8080/api/v1/policy \
  -H "Content-Type: application/json" \
  -d '{"max_risk_score": 0.7, "block_on_not_found": true}'
```

### CI/CD Integration

#### GitHub Actions
```yaml
- name: GuardRail Dependency Scan
  uses: your-org/guardrail@v1
  with:
    manifest: requirements.txt
    strict: true
    fail-on: warn  # or 'block'
```

#### Generic CI
```bash
guardrail scan requirements.txt --format sarif > guardrail-report.sarif
guardrail scan package.json --format json --strict
```

## Scoring Explained

Each package receives a **risk score** from 0.0 (safe) to 1.0 (high risk):

| Score | Level | Action |
|-------|-------|--------|
| 0.0 – 0.3 | LOW | Allow |
| 0.3 – 0.6 | MEDIUM | Warn |
| 0.6 – 0.8 | HIGH | Warn + remediation |
| 0.8 – 1.0 | CRITICAL | Block |

### Risk Factors
- **Registry Existence** (40%): Does the package exist on the registry?
- **Reputation** (30%): Download count, age, maintainer count
- **Heuristics** (30%): Edit distance to known packages, AI naming pattern detection

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GUARDRAIL_POLICY_SERVER` | Policy server URL | (none) |
| `GUARDRAIL_CACHE_TTL` | Cache TTL in seconds | 900 |
| `GUARDRAIL_CACHE_DB` | SQLite cache path | `~/.guardrail/cache.db` |
| `GUARDRAIL_STRICT` | Fail on warnings | false |
| `GUARDRAIL_LOG_LEVEL` | Log level | INFO |

## Running Tests

```bash
pytest tests/ -v
# With coverage
pytest tests/ -v --cov=core --cov-report=html
```