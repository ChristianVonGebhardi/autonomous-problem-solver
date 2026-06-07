#!/usr/bin/env bash
# Convenience script to start all components for local development.
# Requires: PostgreSQL running, Python venv activated, Node installed.

set -e

echo "=== Behavioral Drift Detection Platform ==="
echo ""

# Check PostgreSQL
if ! pg_isready -q 2>/dev/null; then
  echo "⚠️  PostgreSQL not running. Start it or use docker-compose up postgres"
fi

# Initialize DB
echo "→ Initializing database..."
python -m scripts.init_db

# Start API in background
echo "→ Starting API server on :8000..."
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

# Start worker in background
echo "→ Starting drift detection worker..."
python -m workers.run_worker &
WORKER_PID=$!

# Start dashboard
echo "→ Starting dashboard on :5173..."
cd dashboard && npm run dev &
DASH_PID=$!

echo ""
echo "✓ All components started"
echo "  API:       http://localhost:8000"
echo "  API docs:  http://localhost:8000/docs"
echo "  Dashboard: http://localhost:5173"
echo ""
echo "Run simulation: python -m examples.simulate_agent"
echo ""
echo "Press Ctrl+C to stop all components."

# Wait and cleanup
trap "kill $API_PID $WORKER_PID $DASH_PID 2>/dev/null; exit 0" INT TERM
wait