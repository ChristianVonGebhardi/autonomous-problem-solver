#!/bin/bash
# Start all services for local development
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🚀 Starting Flaky Test Detector (dev mode)"
echo ""

# Check Docker
if ! command -v docker &>/dev/null; then
  echo "❌ Docker not found. Please install Docker first."
  exit 1
fi

# Start infrastructure
echo "📦 Starting Postgres + Redis..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up postgres redis -d

# Wait for services
echo "⏳ Waiting for services to be healthy..."
sleep 8

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 not found."
  exit 1
fi

# Set up backend if needed
cd "$ROOT_DIR/backend"
if [ ! -d "venv" ]; then
  echo "🐍 Creating Python virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null || true

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt -q

# Copy .env if needed
if [ ! -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  echo "✅ Created .env from .env.example"
fi

# Initialize DB
echo "🗄️  Initializing database..."
cd "$ROOT_DIR/backend"
python -c "from app.db.init_db import init_database; init_database()"

# Seed demo data
echo "🌱 Seeding demo data..."
python "$ROOT_DIR/backend/scripts/seed_demo_data.py" 2>/dev/null || true

echo ""
echo "✅ Setup complete! Now start these in separate terminals:"
echo ""
echo "  Terminal 1 (API):    cd backend && source venv/bin/activate && uvicorn app.main:app --reload"
echo "  Terminal 2 (Worker): cd backend && source venv/bin/activate && python -m app.workers.flakiness_worker"
echo "  Terminal 3 (Worker): cd backend && source venv/bin/activate && python -m app.workers.fix_worker"
echo "  Terminal 4 (UI):     cd frontend && npm install && npm run dev"
echo ""
echo "  Dashboard:  http://localhost:5173"
echo "  API Docs:   http://localhost:8000/docs"
echo ""