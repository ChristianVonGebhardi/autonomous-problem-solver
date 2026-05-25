# ScopeGuard AI — Scope Creep Detector

An AI-powered SaaS tool that automatically detects when client requests fall outside a signed contract's scope and instantly generates a billable change order.

## Features

- **Contract Ingestion**: Upload PDF, DOCX, or TXT contracts — parsed, chunked, and embedded with OpenAI `text-embedding-3-large` into pgvector
- **AI Scope Analysis**: Paste client messages → GPT-4o compares them against contract clauses via semantic search → violation score + severity
- **Auto Change Order Generation**: GPT-4o drafts a professional change order with estimated hours and cost
- **Real-time Alerts**: WebSocket push notifications when scope creep is detected
- **Revenue Dashboard**: Track recovered revenue from approved change orders
- **PDF Export**: Download change orders as PDF (or HTML fallback)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy, Celery |
| AI | OpenAI GPT-4o + text-embedding-3-large |
| Database | PostgreSQL 16 + pgvector |
| Cache/Queue | Redis 7 |
| Frontend | React 18, TypeScript, Tailwind CSS, Vite |
| PDF | WeasyPrint (HTML fallback if unavailable) |

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose (for PostgreSQL + Redis)
- OpenAI API key with GPT-4o access

## Quick Start

### 1. Clone and configure

```bash
cd scope-creep-detector
cp .env.example .env
```

Edit `.env` and set your `OPENAI_API_KEY`:

```env
OPENAI_API_KEY=sk-your-key-here
```

### 2. Start infrastructure (PostgreSQL + Redis)

```bash
docker-compose up -d
```

Wait for services to be healthy:
```bash
docker-compose ps  # Both should show "healthy"
```

### 3. Set up the backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload --port 8000
```

The API will be available at http://localhost:8000  
API docs at http://localhost:8000/docs

### 4. Set up the frontend

```bash
cd frontend  # from scope-creep-detector/

# Install dependencies
npm install

# Start dev server
npm run dev
```

The app will be available at http://localhost:5173

### 5. (Optional) Start Celery worker

For background task processing (alternative to FastAPI BackgroundTasks):

```bash
cd backend
source venv/bin/activate
celery -A app.worker.celery_app worker --loglevel=info
```

## End-to-End Usage Flow

1. **Register** at http://localhost:5173/register with your name, email, and hourly rate
2. **Upload a Contract** — go to Contracts → Upload Contract (PDF/DOCX/TXT)
3. **Analyze a Message** — go to Analyze Message, select your contract, paste a client message
4. **View Violations** — detected scope creep appears in Violations with severity + cost estimate
5. **Review Change Orders** — auto-generated change orders appear in Change Orders
6. **Approve & Download** — approve the change order and download the PDF

## Sample Test Contract

Create a text file `sample-contract.txt`:

```
FREELANCE WEB DESIGN CONTRACT

SCOPE OF WORK:
This contract covers the design and development of a 5-page website including: 
Home page, About page, Services page, Portfolio page, and Contact page.

DELIVERABLES:
- 5 HTML/CSS pages with responsive design
- Integration with provided CMS
- Basic SEO optimization for provided keywords
- 2 rounds of revisions per page

EXCLUSIONS:
The following are explicitly excluded from this contract:
- Logo design or branding work
- Social media setup or management
- Mobile application development
- Content writing or copywriting
- Photography or video production
- E-commerce functionality
- Ongoing maintenance

PAYMENT TERMS:
Fixed price of $5,000 USD. 50% due upon contract signing, 50% upon completion.

TIMELINE:
Project to be completed within 6 weeks of contract signing.
```

Then paste a client message like:
> "The website looks great! Can you also redesign our logo and set up our Instagram and LinkedIn pages? Oh, and we're thinking we need a mobile app too."

→ ScopeGuard will detect 3 violations and generate a change order.

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key (needs GPT-4o access) |
| `DATABASE_URL` | Yes | PostgreSQL async URL |
| `SYNC_DATABASE_URL` | Yes | PostgreSQL sync URL (for Alembic) |
| `REDIS_URL` | Yes | Redis connection URL |
| `SECRET_KEY` | Yes | JWT signing secret (32+ chars) |
| `SENDGRID_API_KEY` | No | For email delivery of change orders |
| `AWS_ACCESS_KEY_ID` | No | For S3 contract storage (uses local disk if unset) |
| `S3_BUCKET` | No | S3 bucket name |

## Development Notes

### Without OpenAI API Key

The app will still work for contract upload and message submission, but:
- Contracts won't be embedded (no vector search)
- Messages won't be analyzed for scope creep
- No change orders will be generated

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Project Structure

```
scope-creep-detector/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app + WebSocket endpoint
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── schemas.py       # Pydantic schemas
│   │   ├── auth.py          # JWT authentication
│   │   ├── config.py        # Settings (pydantic-settings)
│   │   ├── database.py      # Async DB engine
│   │   ├── worker.py        # Celery tasks
│   │   ├── websocket_manager.py
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── contracts.py
│   │   │   ├── messages.py
│   │   │   ├── violations.py
│   │   │   ├── change_orders.py
│   │   │   └── dashboard.py
│   │   └── services/
│   │       ├── document_parser.py
│   │       ├── embeddings.py
│   │       ├── scope_analyzer.py
│   │       ├── pdf_generator.py
│   │       └── storage.py
│   ├── alembic/
│   │   └── versions/
│   │       └── 001_initial.py
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── api.ts
│       ├── store.ts
│       ├── types.ts
│       ├── components/
│       │   └── Layout.tsx
│       ├── hooks/
│       │   └── useWebSocket.ts
│       └── pages/
│           ├── DashboardPage.tsx
│           ├── ContractsPage.tsx
│           ├── MessagesPage.tsx
│           ├── ViolationsPage.tsx
│           └── ChangeOrdersPage.tsx
├── docker-compose.yml
└── .env.example
```

## Troubleshooting

**pgvector extension not found**
```bash
# Ensure you're using the pgvector Docker image (already in docker-compose.yml)
docker-compose down -v && docker-compose up -d
```

**WeasyPrint installation issues**
WeasyPrint requires system libraries. If installation fails, the app automatically falls back to HTML output.
```bash
# Ubuntu/Debian
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b

# macOS
brew install pango
```

**CORS errors in browser**
Make sure the backend is running on port 8000 and the Vite proxy is configured (it is, in `vite.config.ts`).

**"Contract must be in active status" error**
The contract processing (parsing + embedding) must complete before you can analyze messages. Check the contract status in the Contracts page — it should show "Active" (green).