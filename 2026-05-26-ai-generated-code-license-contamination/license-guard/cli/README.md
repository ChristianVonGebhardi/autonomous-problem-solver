# LicenseGuard CLI

A Go CLI for scanning code files and integrating with git pre-commit hooks.

## Build

```bash
# Install dependencies (creates go.sum)
go mod tidy

# Build
go build -o bin/licenseguard ./cmd/licenseguard/

# Or install globally
go install ./cmd/licenseguard/
```

## Commands

```bash
licenseguard version          # Show version
licenseguard status           # Check API status
licenseguard scan file.py     # Scan a file
licenseguard scan --staged    # Scan staged git changes
licenseguard scan --stdin     # Scan from stdin
licenseguard install-hook     # Install pre-commit hook
licenseguard remove-hook      # Remove pre-commit hook
```

## Configuration

Set API URL via flag, env var, or config file:

```bash
# Flag
licenseguard --api-url http://your-api:8000 scan file.py

# Env var
export LICENSEGUARD_API_URL=http://your-api:8000

# Config file: ~/.licenseguard.yaml
api_url: http://your-api:8000
```