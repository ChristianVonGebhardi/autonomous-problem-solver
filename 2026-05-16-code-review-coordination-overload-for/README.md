# Code Review Coordination Platform MVP

An intelligent code review coordination system that automatically routes pull requests to optimal reviewers based on complexity analysis, reviewer capacity, and expertise matching.

## Overview

This MVP demonstrates the core functionality:
- GitHub webhook ingestion for PR events
- ML-based PR complexity analysis
- Intelligent reviewer routing based on capacity and expertise
- Real-time capacity tracking
- Slack notifications for review assignments
- Analytics dashboard for bottleneck visualization

## Architecture

- **Webhook Ingestion Service (Go)**: Receives and validates GitHub webhooks
- **PR Analysis Engine (Python/FastAPI)**: ML-based complexity scoring
- **Routing Optimizer (Go)**: Assigns PRs to optimal reviewers
- **Capacity Tracker (Go)**: Monitors reviewer availability
- **Notification Dispatcher (Go)**: Sends Slack notifications
- **Analytics Dashboard (React + Go)**: Metrics visualization

## Prerequisites

- Go 1.21+
- Python 3.11+
- Docker and Docker Compose
- Node.js 18+ (for dashboard)
- PostgreSQL 15+
- Redis 7+

## Setup

### 1. Clone and Navigate

```bash
cd code-review-coordinator
```

### 2. Environment Configuration

Create `.env` file:

```bash
# GitHub Integration
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here
GITHUB_TOKEN=ghp_your_personal_access_token

# Slack Integration
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=reviewer
POSTGRES_PASSWORD=reviewer_pass
POSTGRES_DB=code_review_coordinator

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Service Ports
WEBHOOK_SERVICE_PORT=8080
ANALYSIS_SERVICE_PORT=8081
ROUTING_SERVICE_PORT=8082
CAPACITY_SERVICE_PORT=8083
NOTIFICATION_SERVICE_PORT=8084
DASHBOARD_API_PORT=8085
DASHBOARD_UI_PORT=3000
```

### 3. Start Infrastructure

```bash
docker-compose up -d postgres redis
```

Wait for services to be healthy:
```bash
docker-compose ps
```

### 4. Initialize Database

```bash
# Run migrations
go run cmd/migrate/main.go
```

### 5. Install Dependencies

**Go services:**
```bash
go mod download
```

**Python ML service:**
```bash
cd services/analysis-engine
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cd ../..
```

**Dashboard:**
```bash
cd dashboard
npm install
cd ..
```

### 6. Train Initial ML Model (Optional for MVP)

```bash
cd services/analysis-engine
python scripts/train_model.py --bootstrap
cd ../..
```

This creates a baseline model. With real data, retrain weekly.

## Running the Services

### Option A: All Services with Docker Compose

```bash
docker-compose up --build
```

### Option B: Individual Services (Development)

**Terminal 1 - Infrastructure:**
```bash
docker-compose up -d postgres redis
```

**Terminal 2 - Webhook Ingestion:**
```bash
go run cmd/webhook-service/main.go
```

**Terminal 3 - Analysis Engine:**
```bash
cd services/analysis-engine
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

**Terminal 4 - Routing Optimizer:**
```bash
go run cmd/routing-service/main.go
```

**Terminal 5 - Capacity Tracker:**
```bash
go run cmd/capacity-service/main.go
```

**Terminal 6 - Notification Dispatcher:**
```bash
go run cmd/notification-service/main.go
```

**Terminal 7 - Dashboard API:**
```bash
go run cmd/dashboard-api/main.go
```

**Terminal 8 - Dashboard UI:**
```bash
cd dashboard
npm start
```

## Configuring GitHub Webhooks

1. Navigate to your repository settings: `https://github.com/YOUR_ORG/YOUR_REPO/settings/hooks`
2. Click "Add webhook"
3. Set Payload URL: `http://your-server:8080/webhook/github`
4. Set Content type: `application/json`
5. Set Secret: Use the value from `GITHUB_WEBHOOK_SECRET` in `.env`
6. Select events: "Pull requests" and "Pull request reviews"
7. Click "Add webhook"

## Testing the MVP

### 1. Verify Services Are Running

```bash
# Check health endpoints
curl http://localhost:8080/health  # Webhook service
curl http://localhost:8081/health  # Analysis engine
curl http://localhost:8082/health  # Routing service
curl http://localhost:8083/health  # Capacity service
curl http://localhost:8084/health  # Notification service
curl http://localhost:8085/health  # Dashboard API
```

### 2. Simulate a PR Event

```bash
curl -X POST http://localhost:8080/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -H "X-Hub-Signature-256: sha256=test" \
  -d @test-data/sample-pr-event.json
```

### 3. View Dashboard

Open browser: `http://localhost:3000`

You should see:
- Active PR queue
- Reviewer capacity status
- Average time-to-merge metrics
- Bottleneck identification

### 4. Check Logs

```bash
# View all service logs
docker-compose logs -f

# View specific service
docker-compose logs -f webhook-service
```

## API Endpoints

### Webhook Service (Port 8080)
- `POST /webhook/github` - GitHub webhook receiver
- `GET /health` - Health check

### Analysis Engine (Port 8081)
- `POST /analyze` - Analyze PR complexity
- `GET /health` - Health check
- `GET /model/info` - Model metadata

### Routing Service (Port 8082)
- `POST /route` - Assign PR to reviewer
- `GET /assignments` - List active assignments
- `GET /health` - Health check

### Capacity Service (Port 8083)
- `GET /capacity` - Current reviewer capacity
- `POST /capacity/update` - Manual capacity update
- `GET /health` - Health check

### Dashboard API (Port 8085)
- `GET /api/metrics/overview` - System overview
- `GET /api/metrics/reviewers` - Reviewer statistics
- `GET /api/prs/active` - Active PRs
- `GET /api/prs/history` - Historical data
- `GET /health` - Health check

## Key Features Demonstrated

1. **Intelligent Routing**: PRs automatically assigned based on:
   - Reviewer current workload
   - File expertise matching
   - Historical review times
   - PR complexity score

2. **Capacity Tracking**: Real-time monitoring of:
   - Active reviews per person
   - Average review time
   - Availability status

3. **Complexity Analysis**: ML scoring considering:
   - Lines of code changed
   - Number of files
   - File types (risk weighting)
   - Historical merge time for similar PRs

4. **Bottleneck Detection**: Dashboard highlights:
   - Overloaded reviewers
   - Stale PRs (>24 hours)
   - Average wait times by team

## Troubleshooting

**Issue: Webhooks not received**
- Verify ngrok/tunnel if testing locally: `ngrok http 8080`
- Check GitHub webhook delivery history for errors
- Verify `GITHUB_WEBHOOK_SECRET` matches GitHub configuration

**Issue: ML model errors**
- Run bootstrap training: `cd services/analysis-engine && python scripts/train_model.py --bootstrap`
- Check `models/` directory exists and contains `complexity_model.pkl`

**Issue: Database connection errors**
- Ensure PostgreSQL is running: `docker-compose ps postgres`
- Verify connection string in `.env`
- Run migrations: `go run cmd/migrate/main.go`

**Issue: Slack notifications not sending**
- Verify `SLACK_WEBHOOK_URL` is correct
- Test webhook manually: `curl -X POST -H 'Content-type: application/json' --data '{"text":"Test"}' $SLACK_WEBHOOK_URL`

## Development

### Running Tests

```bash
# Go services
go test ./...

# Python ML service
cd services/analysis-engine
pytest tests/
cd ../..

# Dashboard
cd dashboard
npm test
cd ..
```

### Code Structure

```
code-review-coordinator/
├── cmd/                    # Service entry points
│   ├── webhook-service/
│   ├── routing-service/
│   ├── capacity-service/
│   ├── notification-service/
│   ├── dashboard-api/
│   └── migrate/
├── internal/              # Shared Go packages
│   ├── models/           # Data models
│   ├── db/              # Database clients
│   ├── queue/           # Message queue
│   └── config/          # Configuration
├── services/
│   └── analysis-engine/  # Python ML service
│       ├── app/
│       ├── models/
│       └── scripts/
├── dashboard/            # React frontend
│   ├── src/
│   └── public/
├── migrations/           # Database migrations
├── test-data/           # Sample webhooks
└── docker-compose.yml
```

## Production Considerations

**Not included in MVP (required for production):**
- Authentication/authorization for APIs
- Rate limiting and DDoS protection
- Encrypted secrets management (use AWS Secrets Manager, etc.)
- Multi-region deployment
- Comprehensive monitoring (Prometheus/Grafana)
- Blue-green deployment pipeline
- Automated model retraining
- GDPR compliance for team data

## License

MIT License - see LICENSE file for details