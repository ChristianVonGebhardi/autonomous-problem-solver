# ARCHITECTURE.md

## Solution Overview
A real-time cloud spending circuit breaker system that monitors multi-cloud resource provisioning and consumption, automatically halting runaway spending before catastrophic bills accumulate. The system operates as a lightweight sidecar pattern integrated into developer workflows with sub-minute detection latency.

## Technology Choices & Rationale

**Core Runtime:** Go (1.21+) for the circuit breaker engine
- Superior concurrency primitives for handling thousands of concurrent resource monitors
- Low memory footprint critical for sidecar deployment alongside developer workloads
- Native cloud SDK support (AWS, Azure, GCP) with minimal overhead
- Sub-millisecond P99 latency for decision making

**Time-Series Database:** TimescaleDB (PostgreSQL extension)
- Native SQL interface reduces operational complexity vs. specialized TSDBs
- Continuous aggregates provide automatic cost rollups across time windows
- Mature replication and backup ecosystem
- Handles 1M+ metrics/second ingestion at required scale

**Rule Engine:** Embedded CEL (Common Expression Language)
- Allows teams to define spending policies as code without custom DSL
- Type-safe evaluation prevents runtime errors in critical path
- Microsecond evaluation latency vs. interpreted languages

**Developer Interface:** CLI tool + IDE extensions (VSCode, JetBrains)
- Provides pre-provisioning cost estimates before resources are created
- Shows real-time spending dashboards in developer context
- Zero-friction integration into existing workflows

**Action Executor:** Serverless functions (AWS Lambda/Azure Functions/GCP Cloud Functions)
- Executes halt actions (tagging, stopping, terminating resources) in target cloud accounts
- Scales to zero when inactive, reducing operational costs
- Cloud-native IAM integration for secure credential management

## Major Components

1. **Cloud Connectors** (Go services): Poll cloud provider APIs every 30-60 seconds for resource state changes and cost data. Use provider-specific SDKs (AWS SDK v2, Azure SDK, GCP Client Libraries) with exponential backoff and circuit breaking. Deploy as Kubernetes DaemonSets or ECS tasks co-located with workloads.

2. **Metric Ingestion Pipeline** (Go + TimescaleDB): Receives normalized spending metrics from connectors. Implements batching (10-second windows) to reduce database write amplification. Stores raw events in hypertables partitioned by team/project for efficient querying.

3. **Circuit Breaker Engine** (Go): Evaluates CEL rules against time-windowed aggregates every 10 seconds. Maintains in-memory state machines per resource using token bucket algorithm for rate limiting decisions. Publishes breach events to message queue (NATS JetStream for guaranteed delivery).

4. **Action Executor** (Serverless functions): Consumes breach events and executes cloud-native halt actions via IAM roles with least-privilege permissions. Supports multi-level actions: warn (Slack notification), throttle (downscale), halt (stop), terminate (destroy with approval workflow).

5. **Developer Tools** (CLI in Go, IDE extensions in TypeScript):
   - Pre-flight cost estimation using cloud pricing APIs (AWS Price List, Azure Retail Prices, GCP Cloud Billing Catalog)
   - Real-time dashboard showing spending against budgets with visual burn-rate indicators
   - Policy simulator for testing rules before deployment

6. **Policy Repository** (Git-backed): Stores CEL rules as version-controlled YAML manifests. Teams define thresholds (absolute spend, rate of change, per-resource limits) and action escalation paths. Supports policy inheritance (organization → team → project).

## Data Flows

1. **Resource Discovery**: Connectors list cloud resources every minute using pagination-aware APIs. New resources trigger webhook notifications where available (AWS EventBridge, Azure Event Grid) for sub-60s detection.

2. **Cost Attribution**: Raw cloud billing data (AWS Cost Explorer, Azure Cost Management, GCP BigQuery billing export) is enriched with tags and mapped to teams/projects. Handles multi-level cost allocation (shared infrastructure, reserved instances).

3. **Anomaly Detection**: Statistical models (exponential smoothing, seasonal decomposition) flag spending deviations beyond 2σ thresholds. Machine learning is explicitly avoided — simple algorithms are more interpretable for financial decisions.

4. **Alert Routing**: Breaches are routed via team-specific Slack channels, PagerDuty for critical halts, and email for daily digests. Includes cost impact summaries and one-click approval links for policy overrides.

## Deployment Target

**Kubernetes Clusters** (1.24+) in customer's own cloud accounts:
- Helm chart deployment for simplified operations
- Horizontal Pod Autoscaling based on resource count monitored (not traffic)
- StatefulSets for circuit breaker engine to maintain decision state across restarts
- External-DNS integration for automatic ingress configuration

**Alternative for smaller teams**: Docker Compose with managed TimescaleDB (Timescale Cloud) and cloud-hosted NATS to reduce operational burden.

## Known Constraints & Human Assistance Required

**Cloud Provider Credentials**: Requires read-only IAM roles in all monitored accounts + write permissions for halt actions. Organizations must provision these via infrastructure-as-code with audit trails.

**Billing API Access**: 
- AWS: Requires Cost Explorer API enabled (~$0.01/request, adds ~$500/month for 1000-resource org)
- Azure: Requires Cost Management API permissions (free but rate-limited to 200 calls/hour)
- GCP: Requires BigQuery billing export configured (manual setup, ~$5/month storage)

**Slack/PagerDuty Integration**: Requires OAuth apps and webhooks configured by customer admins.

**Historical Data**: Initial deployment requires 30-day lookback for baseline establishment. Cold-start period has higher false positive rates.

**Policy Tuning**: First 2-4 weeks require human calibration of thresholds to match team spending patterns. Auto-tuning via ML is roadmap item, not initial release.

**Shared Resource Attribution**: Multi-tenant infrastructure (shared databases, load balancers) requires manual cost allocation rules that cannot be fully automated.

**Compliance Considerations**: Financial data residency may prohibit SaaS deployment in regulated industries (healthcare, finance). Solution must support air-gapped deployment with local-only data storage.

## Architecture Diagram

```mermaid
flowchart TB
    subgraph DevWorkflow["Developer Workflow"]
        CLI[CLI Tool]
        IDE[IDE Extensions]
        PreFlight[Pre-flight Cost Estimator]
    end

    subgraph CloudProviders["Cloud Providers"]
        AWS[AWS Account]
        Azure[Azure Subscription]
        GCP[GCP Project]
    end

    subgraph CircuitBreakerSystem["Circuit Breaker System (K8s Cluster)"]
        subgraph Connectors["Cloud Connectors (Go DaemonSets)"]
            AWSConn[AWS Connector]
            AzureConn[Azure Connector]
            GCPConn[GCP Connector]
        end
        
        MQ[NATS JetStream<br/>Message Queue]
        
        Ingest[Metric Ingestion<br/>Pipeline (Go)]
        
        TSDB[(TimescaleDB<br/>Time-Series Metrics)]
        
        CBEngine[Circuit Breaker Engine<br/>CEL Rule Evaluator]
        
        PolicyRepo[(Policy Repository<br/>Git-backed YAML)]
        
        subgraph Actions["Action Executors"]
            AWSLambda[AWS Lambda]
            AzureFunc[Azure Function]
            GCPFunc[GCP Cloud Function]
        end
    end

    subgraph Alerting["Alerting & Notifications"]
        Slack[Slack Channels]
        PagerDuty[PagerDuty]
        Email[Email Digests]
    end

    subgraph BillingAPIs["Cloud Billing APIs"]
        AWSCost[AWS Cost Explorer API]
        AzureCost[Azure Cost Management API]
        GCPBilling[GCP BigQuery Billing Export]
    end

    CLI --> PreFlight
    IDE --> PreFlight
    PreFlight --> AWSCost
    PreFlight --> AzureCost
    PreFlight --> GCPBilling

    AWSConn -->|Resource State| AWS
    AzureConn -->|Resource State| Azure
    GCPConn -->|Resource State| GCP
    
    AWSConn -->|Cost Data| AWSCost
    AzureConn -->|Cost Data| AzureCost
    GCPConn -->|Cost Data| GCPBilling

    AWSConn --> Ingest
    AzureConn --> Ingest
    GCPConn --> Ingest

    Ingest --> TSDB

    TSDB -->|Aggregated Metrics| CBEngine
    PolicyRepo -->|CEL Rules| CBEngine

    CBEngine -->|Breach Events| MQ

    MQ --> AWSLambda
    MQ --> AzureFunc
    MQ --> GCPFunc

    AWSLambda -->|Halt Actions| AWS
    AzureFunc -->|Halt Actions| Azure
    GCPFunc -->|Halt Actions| GCP

    CBEngine --> Slack
    CBEngine --> PagerDuty
    CBEngine --> Email

    CLI -.->|Real-time Dashboard| TSDB
    IDE -.->|Spending Widgets| TSDB

    style CircuitBreakerSystem fill:#e1f5ff
    style DevWorkflow fill:#fff4e1
    style CloudProviders fill:#ffe1e1
    style Alerting fill:#e1ffe1
```
