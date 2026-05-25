# AI-Powered Scope Creep Detector

An MVP SaaS application that detects when client requests fall outside a signed contract's scope and auto-generates billable change orders.

## Architecture Overview

- **Backend**: Python + FastAPI (async REST API + WebSockets)
- **Frontend**: React + TypeScript
- **Database**: PostgreSQL with pgvector extension
- **Cache/Queue**: Redis + Celery
- **AI**: OpenAI GPT-4o + text-embedding-3-large
- **PDF Parsing**: PyMuPDF + Unstructured

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- OpenAI API key

## Quick Start

### 1. Clone and Configure

```bash
cd scope-creep-detector
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 2. Start Infrastructure (PostgreSQL + Redis)

```bash
docker-compose up -d postgres redis
```

### 3. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start FastAPI server
uvicorn app.main:app --reload --port 8000
```

### 4. Start Celery Worker (in a new terminal)

```bash
cd backend
source venv/bin/activate
celery -A app.worker worker --loglevel=info
```

### 5. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 6. Access the Application

- Frontend: http://localhost:5173
- API Docs: http://localhost:8000/docs
- API: http://localhost:8000

## Environment Variables

See `.env.example` for all required variables. Key ones:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key (required) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | JWT signing secret |
| `SENDGRID_API_KEY` | Optional: for email delivery |

## Demo Flow

1. **Register/Login** at http://localhost:5173
2. **Upload a contract** (PDF or DOCX) on the Contracts page
3. **Simulate a client message** on the Messages page (or use the "Analyze Message" button)
4. **View alerts** on the Dashboard — scope violations appear in real-time
5. **Review and approve** auto-generated change orders
6. **Track recovered revenue** in the Dashboard metrics

## API Endpoints

### Auth
- `POST /api/auth/register` — Create account
- `POST /api/auth/login` — Get JWT token

### Contracts
- `POST /api/contracts/upload` — Upload PDF/DOCX contract
- `GET /api/contracts/` — List contracts
- `GET /api/contracts/{id}` — Get contract details

### Messages
- `POST /api/messages/analyze` — Submit message for scope analysis
- `GET /api/messages/` — List analyzed messages

### Violations
- `GET /api/violations/` — List detected violations
- `GET /api/violations/{id}` — Get violation details

### Change Orders
- `GET /api/change-orders/` — List change orders
- `POST /api/change-orders/{id}/approve` — Approve and send
- `GET /api/change-orders/{id}/pdf` — Download PDF

## Running Tests

```bash
cd backend
pytest tests/ -v
```