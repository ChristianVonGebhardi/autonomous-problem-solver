#!/bin/bash
# Quick local development setup
set -e

echo "🔍 LicenseGuard Backend - Local Setup"
echo "======================================"

# Check for .env
if [ ! -f .env ]; then
    echo "📋 Creating .env from .env.example..."
    cp ../.env.example .env
fi

# Load env
source .env 2>/dev/null || true

# Run migrations
echo "📦 Running database migrations..."
python -m alembic upgrade head

# Seed corpus if empty
echo "🌱 Seeding corpus..."
python scripts/seed_corpus.py

# Start server
echo "🚀 Starting API server..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload