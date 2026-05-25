# ScopeGuard AI — AI-Powered Scope Creep Detector

Stop losing money to scope creep. ScopeGuard AI monitors client messages against your signed contracts in real time, automatically flags out-of-scope work, and generates professional change orders ready to send.

## Features

- 📄 **Contract ingestion** — Upload PDF/DOCX/TXT contracts; clauses are chunked and embedded with OpenAI `text-embedding-3-large` into pgvector
- 🔍 **AI scope analysis** — GPT-4o compares every client message against relevant contract clauses via semantic search
- ⚡ **Real-time alerts** — WebSocket push notifications when scope creep is detected
- 📋 **Auto-generated change orders** — Professional change order documents with cost estimates, ready for client delivery
- 📊 **Revenue dashboard** — Track recovered vs. potential billable revenue across all projects

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy async |
| AI | OpenAI GPT-4o + text-embedding-3-large |
| Database | PostgreSQL 16 + pgvector |
| Queue | Redis + Celery (optional) |
| Frontend | React 18 + TypeScript + Tailwind CSS |
| PDF | WeasyPrint (falls back to HTML) |

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- OpenAI API key with GPT-4o access

## Setup

### 1. Clone and configure environment

```bash
cd scope-creep-detector

# Copy environment file
cp .env.example .env
```

Edit `.env` and set at minimum:
```
OPENAI_API_KEY=sk-your-key-here
SECRET_KEY=any-random-32-char-string
```

### 2. Start PostgreSQL and Redis

```bash
docker-compose up -d
```

Wait for services to be healthy:
```bash
docker-compose ps
```

### 3. Install backend dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> **Note on WeasyPrint**: If WeasyPrint fails to install (it requires system libraries), the app will fall back to generating HTML change orders instead of PDFs. On Ubuntu: `sudo apt-get install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0`. On macOS: `brew install pango`.

### 4. Run database migrations

The app auto-creates tables on startup, but you can also use Alembic:

```bash
cd backend
alembic upgrade head
```

### 5. Start the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The API will be available at http://localhost:8000  
API docs: http://localhost:8000/docs

### 6. Install and start the frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at http://localhost:5173

## Usage

### End-to-End Flow

1. **Register** at http://localhost:5173/register
   - Enter your name, email, password, and hourly rate

2. **Upload a contract** at `/contracts`
   - Upload any PDF or DOCX contract (or a sample text file)
   - The system will parse and index it with embeddings

3. **Analyze a message** at `/messages`
   - Select your contract
   - Try one of the sample messages (e.g., "Can you also build a mobile app?")
   - Click "Analyze for Scope Creep"

4. **Review violations** at `/violations`
   - AI-detected violations appear with severity, score, and cited clauses
   - Expand to see the full analysis

5. **Approve change orders** at `/change-orders`
   - Auto-generated change orders appear for each violation
   - Edit the details, approve, and download the PDF

### Sample Contract Text

If you don't have a contract handy, create a `sample.txt` file with content like:

```
STATEMENT OF WORK

Project: Website Redesign for Acme Corp

SCOPE OF WORK:
This contract covers the design and development of a 5-page marketing website 
including: Home, About, Services, Portfolio, and Contact pages.

DELIVERABLES:
- Custom responsive website design (desktop + mobile)
- WordPress theme implementation
- Contact form integration
- Basic SEO setup (meta tags, sitemap)

NOT INCLUDED / OUT OF SCOPE:
- Logo design or brand identity work
- Content writing or copywriting
- Social media setup or management
- E-commerce functionality
- Mobile application development
- Ongoing maintenance after launch

REVISIONS:
Up to 2 rounds of revisions are included per page.
Additional revisions are billed at $150/hour.

PROJECT VALUE: $5,000 fixed price
TIMELINE: 6 weeks from project kickoff
```

Then upload this file and analyze messages like:
- "Can you also design our logo while you're at it?"
- "We need a mobile app version too"
- "Could you write the copy for all the pages?"

## Architecture Notes

### Without OpenAI API key
The app will still run but won't analyze messages for scope creep. Contracts will be uploaded and stored, but violations won't be detected.

### Without Celery
Message analysis runs inline as FastAPI background tasks (sufficient for MVP/demo). For production load, start a Celery worker:

```bash
cd backend
celery -A app.worker.celery_app worker --loglevel=info
```

### Database schema
The `CREATE EXTENSION IF NOT EXISTS vector` is executed automatically on startup. pgvector enables semantic clause retrieval via cosine similarity (`<=>` operator).

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/register` | POST | Create account |
| `/api/auth/login` | POST | Authenticate |
| `/api/contracts/upload` | POST | Upload contract file |
| `/api/contracts/` | GET | List contracts |
| `/api/messages/analyze` | POST | Submit message for analysis |
| `/api/violations/` | GET | List detected violations |
| `/api/violations/{id}/dismiss` | POST | Dismiss a violation |
| `/api/change-orders/` | GET | List change orders |
| `/api/change-orders/{id}/approve` | POST | Approve a change order |
| `/api/change-orders/{id}/pdf` | GET | Download PDF |
| `/api/dashboard/stats` | GET | Revenue and activity stats |
| `/ws/{user_id}` | WS | Real-time notifications |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4o |
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `SECRET_KEY` | Yes | JWT signing key (32+ chars) |
| `SENDGRID_API_KEY` | No | For email delivery of change orders |
| `AWS_ACCESS_KEY_ID` | No | S3 storage (falls back to local) |

## Troubleshooting

**pgvector error on startup**: Make sure you're using the `pgvector/pgvector:pg16` Docker image, not standard postgres.

**WeasyPrint fails**: Change orders fall back to HTML automatically. Install system dependencies if you need PDF output.

**Analysis not running**: Ensure `OPENAI_API_KEY` is set and has GPT-4o access. Check backend logs for errors.

**WebSocket not connecting**: The Vite proxy in `vite.config.ts` forwards `/ws` to the backend. Make sure both servers are running.