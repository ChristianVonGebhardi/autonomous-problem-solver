#!/bin/bash
set -e

echo "Starting ScopeGuard AI Backend..."

# Wait for postgres
echo "Waiting for PostgreSQL..."
until python -c "import psycopg2; psycopg2.connect('${SYNC_DATABASE_URL:-postgresql://scopecreep:scopecreep@localhost:5432/scopecreep}')" 2>/dev/null; do
  echo "PostgreSQL not ready, retrying in 2s..."
  sleep 2
done
echo "PostgreSQL is ready."

# Run migrations
echo "Running database migrations..."
alembic upgrade head

# Start server
echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload