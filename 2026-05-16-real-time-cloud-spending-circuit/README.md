# Cloud Spending Circuit Breaker

A real-time cloud spending circuit breaker system that monitors multi-cloud resource provisioning and automatically halts runaway spending before catastrophic bills accumulate.

## Problem

Development teams accidentally spin up runaway cloud resources — misconfigured loops, forgotten GPU instances, exploding data pipelines — causing bills like [$34,000 in 8 days](https://news.ycombinator.com/item?id=28398936). Existing tools do post-facto analysis. This system fires circuit breakers in real time.

## Architecture

```
Cloud Resources → Connectors → Metric Store → Circuit Breaker Engine → Actions
                                                        ↑
                                               CEL Policy Rules (YAML)
```

- **Circuit Breaker Engine**: Evaluates CEL rules every 5–10 seconds against spending windows
- **CEL Policies**: Type-safe, version-controlled spending rules (e.g., `team_spend > threshold`)
- **Simulator**: Demonstrates runaway spending scenario without real AWS credentials
- **CLI Tool**: Pre-flight cost estimates, policy management, real-time dashboard
- **TimescaleDB**: Time-series metrics with continuous aggregates (optional — demo uses in-memory store)
- **NATS JetStream**: Guaranteed breach event delivery (optional — demo uses in-memory queue)

## Prerequisites

- Go 1.21+
- (Optional) Docker + Docker Compose for full stack with TimescaleDB + NATS

## Quick Start — Demo Mode (No Cloud Credentials Required)

```bash
# Clone and install dependencies
git clone <repo>
cd cloud-circuit-breaker
go mod download
go mod tidy

# Run the interactive demo (90 seconds, simulates runaway spending)
go run ./cmd/cli demo

# Show spending status with seeded historical data
go run ./cmd/cli status

# Show cost estimate before provisioning
go run ./cmd/cli estimate --type m5.2xlarge --hours 24 --team data

# List available policies
go run ./cmd/cli policy list

# Validate a policy file
go run ./cmd/cli policy validate configs/policies.yaml
```

## Running the Server

```bash
# Demo server — runs in-memory, no DB required
go run ./cmd/server

# With a custom policy file
POLICY_FILE=configs/policies.yaml go run ./cmd/server
```

## Running with Full Stack (TimescaleDB + NATS)

```bash
# Start infrastructure
docker-compose -f configs/docker-compose.yml up -d

# Wait for health checks
docker-compose -f configs/docker-compose.yml ps

# Run server with real DB
DATABASE_URL="postgres://ccb:ccbpassword@localhost:5432/circuitbreaker" \
NATS_URL="nats://localhost:4222" \
go run ./cmd/server
```

## Running Tests

```bash
# All tests
go test ./...

# Circuit breaker engine tests with verbose output
go test -v ./internal/engine/...

# Run tests with race detector
go test -race ./...
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `ccb demo` | Run 90-second interactive demo with runaway spending simulation |
| `ccb status` | Show current spending status and circuit breaker states |
| `ccb estimate --type t3.large --hours 24 --team myteam` | Pre-flight cost estimate with policy check |
| `ccb policy list` | List all policies with their status |
| `ccb policy validate <file>` | Validate a policy YAML file |

## Writing Policies

Policies are YAML files with CEL expressions. Example:

```yaml
version: "1.0"
policies:
  - id: my-team-daily-limit
    name: "My Team Daily Spend Limit"
    team: my-team
    project: "*"
    enabled: true
    cel_expression: "team_spend > threshold"
    threshold_amount: 100.0
    time_window: "24h"
    actions:
      - type: notify
        severity: warn
      - type: halt
        severity: critical
```

### Available CEL Variables

| Variable | Type | Description |
|----------|------|-------------|
| `team_spend` | double | Total team spend in time window |
| `project_spend` | double | Total project spend in time window |
| `resource_spend` | double | Individual resource spend |
| `hourly_rate` | double | Derived hourly spending rate |
| `daily_rate` | double | Derived daily spending rate |
| `threshold` | double | Configured threshold amount |
| `team` | string | Team name |
| `project` | string | Project name |
| `resource_id` | string | Resource identifier |

### Example CEL Expressions

```
# Simple threshold
team_spend > threshold

# Hourly rate guard (catches runaway loops fast)
hourly_rate > 10.0

# Compound rule
team_spend > threshold && daily_rate > 20.0

# Project-specific
project_spend > 500.0

# High-velocity detection
hourly_rate > threshold / 24 * 3
```

### Time Windows

| Value | Description |
|-------|-------------|
| `1h` | Last 1 hour |
| `6h` | Last 6 hours |
| `12h` | Last 12 hours |
| `24h` | Last 24 hours |
| `7d` | Last 7 days |
| `30d` | Last 30 days |

### Action Types

| Type | Effect |
|------|--------|
| `notify` | Send Slack/email notification |
| `throttle` | Downscale instance type |
| `halt` | Stop running resources |
| `terminate` | Terminate resources (requires approval) |

## Demo Scenario

The demo simulates a common real-world incident:

1. **Normal operations**: `platform` team runs t3.medium + m5.xlarge for API gateway
2. **Data team starts ML training**: Spins up r5.xlarge + m5.2xlarge
3. **Runaway resource appears**: `i-0runaway999` starts with normal cost then exponentially escalates (simulating a misconfigured training loop)
4. **Circuit breaker fires**: `data-hourly-runaway-guard` policy detects `hourly_rate > $10/hr`
5. **Actions execute**: Notification sent, halt action dispatched

```
[15:04:05] team=data        spend=$0.0012     hourly_rate=$0.0012/hr   threshold=$10.00 — ✅ OK
[15:04:10] team=data        spend=$0.0234     hourly_rate=$1.4040/hr   threshold=$10.00 — ✅ OK
[15:04:15] team=data        spend=$0.8921     hourly_rate=$53.526/hr   threshold=$10.00 — 🚨 BREACH! Actions: [notify halt]
```

## Project Structure

```
.
├── cmd/
│   ├── server/main.go       # Demo server (in-memory, no DB required)
│   └── cli/main.go          # CLI tool
├── internal/
│   ├── actions/
│   │   └── executor.go      # Breach action executor
│   ├── connectors/
│   │   └── aws_connector.go # AWS resource + cost discovery
│   ├── database/
│   │   ├── db.go            # TimescaleDB operations
│   │   └── schema.sql       # Database schema with hypertables
│   ├── engine/
│   │   ├── circuit_breaker.go      # CEL rule evaluator
│   │   └── circuit_breaker_test.go # Engine tests
│   ├── models/
│   │   └── resource.go      # Core data models
│   ├── policy/
│   │   └── loader.go        # YAML policy loader + validator
│   ├── queue/
│   │   └── nats.go          # NATS JetStream + in-memory queue
│   └── simulator/
│       └── simulator.go     # Demo scenario simulator
├── configs/
│   ├── policies.yaml        # Example policy definitions
│   └── docker-compose.yml   # TimescaleDB + NATS stack
├── go.mod
└── README.md
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (none) | PostgreSQL/TimescaleDB connection string |
| `NATS_URL` | `nats://localhost:4222` | NATS server URL |
| `POLICY_FILE` | `configs/policies.yaml` | Path to policy YAML |
| `SLACK_WEBHOOK` | (none) | Slack incoming webhook URL |
| `DRY_RUN` | `true` | When true, logs actions without executing |
| `AWS_REGION` | `us-east-1` | AWS region for connector |

## AWS Connector (requires credentials)

To use real AWS data instead of the simulator:

```bash
# Configure AWS credentials
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1

# The connector requires:
# - ec2:DescribeInstances (read-only)
# - ce:GetCostAndUsage (Cost Explorer read)
```

IAM policy for read-only monitoring:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"],
      "Resource": "*"
    },
    {
      "Effect": "Allow", 
      "Action": ["ce:GetCostAndUsage", "ce:GetCostForecast"],
      "Resource": "*"
    }
  ]
}
```