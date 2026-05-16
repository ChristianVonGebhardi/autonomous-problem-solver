# Healthcare Referral Coordination Platform - MVP

## Overview
A HIPAA-compliant referral orchestration platform that automates the referral lifecycle from order creation to specialist consultation. This MVP demonstrates:
- HL7 FHIR referral ingestion
- Automated specialist matching based on insurance and location
- Patient engagement via SMS/Email
- Prior authorization workflow (simulated)
- Real-time tracking dashboard
- Specialist portal for referral management

## Architecture
- **Backend**: Java 17 + Spring Boot 3.2
- **Event Bus**: Apache Kafka (embedded for MVP)
- **Workflow Engine**: Temporal.io
- **Database**: PostgreSQL with PostGIS
- **Cache**: Redis
- **Patient Engagement**: Twilio (with mock mode) + SendGrid (with mock mode)
- **AI Integration**: Azure OpenAI (with mock mode)
- **Frontend**: React SPA

## Prerequisites
- Java 17+
- Docker & Docker Compose
- Maven 3.8+
- Node.js 18+ (for frontend)

## Quick Start

### 1. Start Infrastructure Services
```bash
docker-compose up -d
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- Kafka + Zookeeper (port 9092)
- Temporal Server (port 7233)

### 2. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env with your configuration (optional for MVP, defaults work with mock mode)
```

Required for production (MVP uses mock mode by default):
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_DEPLOYMENT`

### 3. Build and Run Backend
```bash
cd referral-platform
mvn clean install
mvn spring-boot:run
```

Backend runs on http://localhost:8080

### 4. Run Frontend (separate terminal)
```bash
cd referral-platform/src/main/frontend
npm install
npm start
```

Frontend runs on http://localhost:3000

## Testing the MVP

### 1. Submit a Test Referral (via FHIR API)
```bash
curl -X POST http://localhost:8080/api/fhir/ServiceRequest \
  -H "Content-Type: application/json" \
  -d @test-data/sample-referral.json
```

### 2. Access Dashboard
Open http://localhost:3000/dashboard to view:
- Real-time referral status
- Specialist matches
- Patient engagement history
- Workflow progress

### 3. Specialist Portal
Open http://localhost:3000/specialist to:
- View incoming referrals
- Accept/reject referrals
- Upload consultation notes

### 4. View Workflow Status
```bash
# Check Temporal workflows
curl http://localhost:8080/api/workflows
```

## API Endpoints

### FHIR Gateway
- `POST /api/fhir/ServiceRequest` - Submit new referral
- `GET /api/fhir/ServiceRequest/{id}` - Get referral status
- `PUT /api/fhir/ServiceRequest/{id}` - Update referral

### Referral Management
- `GET /api/referrals` - List all referrals
- `GET /api/referrals/{id}` - Get referral details
- `POST /api/referrals/{id}/assign` - Assign specialist
- `PUT /api/referrals/{id}/status` - Update status

### Specialist Management
- `GET /api/specialists` - List specialists (with filters)
- `POST /api/specialists` - Register new specialist
- `GET /api/specialists/match` - Find matching specialists

### Analytics
- `GET /api/analytics/dashboard` - Dashboard metrics
- `GET /api/analytics/leakage` - Referral leakage funnel
- `GET /api/analytics/performance` - Processing time metrics

## Development

### Run Tests
```bash
mvn test
```

### Database Migrations
```bash
mvn flyway:migrate
```

### View Temporal UI
Open http://localhost:8088 to view workflow executions

## Project Structure
```
referral-platform/
├── src/main/java/com/healthtech/referral/
│   ├── config/          # Spring configuration
│   ├── controller/      # REST controllers
│   ├── service/         # Business logic
│   ├── workflow/        # Temporal workflows
│   ├── integration/     # External integrations
│   ├── repository/      # Data access
│   └── model/           # Domain models
├── src/main/resources/
│   ├── application.yml  # Spring config
│   └── db/migration/    # Flyway scripts
├── src/main/frontend/   # React application
└── src/test/            # Tests
```

## Mock Mode
The MVP runs in mock mode by default for external services:
- **Twilio**: Logs SMS instead of sending
- **SendGrid**: Logs emails instead of sending  
- **Azure OpenAI**: Returns simulated responses
- **Payer Portals**: Simulates prior auth approval

To enable real integrations, set environment variables and set `MOCK_MODE=false`

## Troubleshooting

### Kafka Connection Issues
```bash
docker-compose restart kafka
```

### Temporal Connection Issues
```bash
docker-compose restart temporal
```

### Database Issues
```bash
docker-compose down -v
docker-compose up -d
mvn flyway:clean flyway:migrate
```

## Production Deployment Notes
For production deployment:
1. Use managed Kafka (AWS MSK, Confluent Cloud)
2. Use Temporal Cloud or dedicated cluster
3. Deploy to Kubernetes with proper HIPAA controls
4. Enable TLS/SSL for all connections
5. Set up proper monitoring (Prometheus/Grafana)
6. Configure HIPAA-compliant logging
7. Implement proper access controls and audit trails
8. Sign Business Associate Agreements with all vendors

## License
Proprietary - Healthcare Technology Solutions Inc.