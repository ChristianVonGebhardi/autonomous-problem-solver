#!/usr/bin/env bash
# Run GuardRail test suite

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "Installing dependencies..."
pip install -e ".[dev]" -q 2>/dev/null || pip install -e . -q

echo ""
echo "Running GuardRail test suite..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python -m pytest tests/ -v --tb=short

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "All tests passed!"