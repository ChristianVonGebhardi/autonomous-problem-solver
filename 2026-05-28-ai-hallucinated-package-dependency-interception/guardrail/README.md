# GuardRail — AI Package Hallucination Interception

GuardRail validates AI-generated package dependencies against live registries, heuristics, and reputation data to prevent slopsquatting supply-chain attacks.

## What It Does

- **Registry Check**: Queries PyPI, npm, crates.io, Go module proxy, and Maven Central to verify packages exist
- **Heuristic Analysis**: Detects AI-hallucinated naming patterns using edit-distance, phonetic similarity, and structural analysis
- **Reputation Scoring**: Evaluates download counts, publish dates, and maintainer signals
- **CI/CD Gate**: GitHub Actions integration that blocks PRs introducing suspicious dependencies
- **Package Manager Shims**: Wraps `pip` and `npm` to intercept installs before they execute

## Quick Start

### Prerequisites

- Python 3.9+
- pip

### Installation

```bash
cd guardrail
pip install -e .
```

### Scan a manifest file

```bash
# Scan a requirements.txt
guardrail scan requirements.txt

# Scan package.json
guardrail scan package.json

# Scan with JSON output
guardrail scan requirements.txt --format json

# Scan with SARIF output (for GitHub Code Scanning)
guardrail scan requirements.txt --format sarif --output results.sarif
```

### Check a single package

```bash
# Check if a PyPI package is safe
guardrail check requests --ecosystem pypi

# Check an npm package
guardrail check lodash --ecosystem npm

# Check a suspicious package
guardrail check numpy-helper-utils --ecosystem pypi
```

### Install package manager shims

```bash
# Install pip shim
guardrail install-shim pip

# Add to PATH (add to ~/.bashrc or ~/.zshrc)
export PATH="$HOME/.guardrail/shims:$PATH"

# Now all pip install commands are intercepted
pip install some-package  # GuardRail validates before installing
```

## Output Formats

### Table (default)
```
╭─────────────────────────────────────────────────────────────────╮
│ GuardRail Scan: requirements.txt                                │
├────────────────────┬──────────┬───────────┬───────┬────────────┤
│ Package            │ Ecosys.  │ Risk      │ Score │ Exists     │
├────────────────────┼──────────┼───────────┼───────┼────────────┤
│ requests           │ pypi     │ ✓ LOW     │ 0.05  │ ✓          │
│ numpy-helper-utils │ pypi     │ ✗ CRITICAL│ 0.92  │ ✗          │
╰────────────────────┴──────────┴───────────┴───────┴────────────╯
```

### JSON
```json
{
  "manifest_path": "requirements.txt",
  "ecosystem": "pypi",
  "summary": {"total": 5, "blocked": 1, "warned": 1, "clean": 3},
  "results": [...]
}
```

### SARIF (for GitHub Code Scanning upload)
```bash
guardrail scan requirements.txt --format sarif --output guardrail.sarif
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/guardrail.yml
name: GuardRail Dependency Scan
on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install GuardRail
        run: pip install guardrail-cli
      - name: Scan dependencies
        run: guardrail scan requirements.txt --format sarif --output guardrail.sarif
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: guardrail.sarif
```

### Generic CI (fail on blocked packages)

```bash
guardrail scan requirements.txt --fail-on block
```

Exit codes:
- `0` — all packages clean (or only warnings with `--fail-on block`)
- `1` — blocked packages found (or warnings with `--fail-on warn`)
- `2` — configuration error

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GUARDRAIL_CACHE_DB` | SQLite cache path | `~/.guardrail/cache.db` |
| `GUARDRAIL_CACHE_TTL` | Cache TTL in seconds | `900` (15 min) |
| `GUARDRAIL_POLICY_SERVER` | Policy server URL | (none) |

### Policy Server (Optional)

For team-level allow/block lists:

```bash
# Start the policy server
cd policy_server
go build -o guardrail-policy .
./guardrail-policy --port 8080

# Use with scanner
guardrail scan requirements.txt --policy-server http://localhost:8080
```

## Risk Levels

| Level | Score | Meaning |
|-------|-------|---------|
| LOW | < 0.30 | Package appears legitimate |
| MEDIUM | 0.30–0.59 | Some concerns, review recommended |
| HIGH | 0.60–0.79 | Significant red flags |
| CRITICAL | ≥ 0.80 | Block installation — likely hallucinated or malicious |

## Running Tests

```bash
cd guardrail
pip install -e ".[dev]"
pytest tests/ -v

# With coverage
pytest tests/ --cov=core --cov-report=html
```

## Architecture

```
guardrail/
├── cli/           # Click CLI entry points
├── core/          # Validation engine
│   ├── validator.py    # Orchestrator (parallel checks)
│   ├── registry.py     # Registry API clients
│   ├── heuristics.py   # AI naming pattern detection
│   ├── reputation.py   # Download/age/maintainer scoring
│   ├── cache.py        # SQLite TTL cache
│   ├── parsers.py      # Manifest file parsers
│   └── models.py       # Data models
├── tests/         # pytest test suite
└── policy_server/ # Optional Go policy server
```

## License

MIT