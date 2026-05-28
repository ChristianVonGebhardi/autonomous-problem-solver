#!/usr/bin/env bash
# GuardRail MVP Demo Script
# Demonstrates end-to-end scanning of manifest files

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLES_DIR="$SCRIPT_DIR/../examples"

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║            GuardRail — AI Package Interception            ║"
echo "║                   MVP Demo                                ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Check guardrail is installed
if ! command -v guardrail &>/dev/null; then
    echo "Installing GuardRail..."
    cd "$SCRIPT_DIR/.."
    pip install -e . -q
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 1: Check a known-safe package (requests)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
guardrail check requests --ecosystem pypi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 2: Check a hallucinated package (numpy-ai-helper-toolkit)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
guardrail check numpy-ai-helper-toolkit --ecosystem pypi || true
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 3: Check a typosquat attempt (reqests → requests)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
guardrail check reqests --ecosystem pypi || true
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 4: Scan the mixed requirements.txt example"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
guardrail scan "$EXAMPLES_DIR/requirements_mixed.txt" || true
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 5: Scan the mixed package.json example (npm)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
guardrail scan "$EXAMPLES_DIR/package_mixed.json" --ecosystem npm || true
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 6: JSON output format"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
guardrail scan "$EXAMPLES_DIR/requirements_mixed.txt" --format json | python3 -m json.tool | head -40
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 7: SARIF output format"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
guardrail scan "$EXAMPLES_DIR/requirements_mixed.txt" --format sarif --output /tmp/guardrail.sarif
echo "SARIF written to /tmp/guardrail.sarif"
cat /tmp/guardrail.sarif | python3 -m json.tool | head -30
echo ""

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                     Demo Complete!                        ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  • Install shim: guardrail install-shim pip"
echo "  • Run tests:    pytest tests/ -v"
echo "  • VS Code ext:  Open vscode-extension/ in VS Code"
echo "  • Policy server: cd policy_server && go build && ./guardrail-policy"
echo ""