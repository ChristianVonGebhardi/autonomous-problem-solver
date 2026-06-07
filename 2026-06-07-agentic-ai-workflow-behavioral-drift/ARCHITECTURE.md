The solution is a behavioral telemetry and drift detection platform, deployed as a lightweight sidecar-plus-control-plane architecture that sits alongside existing agentic workflows without requiring agents to be rebuilt. The core insight is that behavioral drift must be detected across three distinct signal layers: **structural** (tool selection sequences, step ordering), **semantic** (embedding-space distance between intended and actual reasoning), and **distributional** (output token distributions, confidence signals, retrieval quality scores). Combining these three layers into a unified drift score is what separates this from both infrastructure monitoring and naive LLM-as-judge approaches.

**Technology choices:** The instrumentation SDK is Python (the dominant language for agentic frameworks like LangChain, LlamaIndex, CrewAI, AutoGen), exposing OpenTelemetry-compatible spans enriched with behavioral attributes — tool names, step indices, retrieved chunk hashes, reasoning chain embeddings. This plugs into existing OTEL collectors so infrastructure teams have zero new ingestion pipelines to operate. The streaming pipeline uses Apache Kafka because agent traces arrive as event streams with variable cardinality, and Kafka's log compaction enables replay for retrospective baselining. The analytical backend is TimescaleDB (PostgreSQL extension) for time-series drift metrics with SQL familiarity, plus Qdrant as a vector store for embedding-based semantic baseline comparisons. Drift detection algorithms run in Python workers using statistical process control (CUSUM, EWMA) for distributional signals and cosine distance decay for semantic signals — no LLM-in-the-loop needed for core detection, keeping latency and cost low. An optional LLM-powered explainability layer (calling GPT-4o or Claude via API) generates human-readable drift summaries only on alert, gating cost behind actual signal. The control plane API is FastAPI; the dashboard is React with Recharts. Deployment target is Kubernetes with Helm charts, designed for enterprise on-premise or VPC deployment given data sensitivity.

**Known constraints:** Semantic baselining requires a corpus of "golden run" traces — human assistance needed to curate initial baselines per workflow. LLM explainability requires an API key for a frontier model. Highly customized agent frameworks may need bespoke SDK adapters.

## Architecture Diagram

```mermaid
flowchart TB
    subgraph Enterprise_Agent_Runtime["Enterprise Agent Runtime"]
        A1[Agent Step 1\nTool Calls / Reasoning]
        A2[Agent Step 2\nRetrieval / Planning]
        A3[Agent Step N\nOutput / Action]
        A1 --> A2 --> A3
    end

    subgraph Instrumentation_Layer["Instrumentation Layer"]
        SDK[BehaviorTrace SDK\nOTEL-compatible\nPython Middleware]
        ENRICHER[Span Enricher\nTool names, step index\nembeddings, chunk hashes\nconfidence scores]
        SDK --> ENRICHER
    end

    subgraph Ingestion_Pipeline["Streaming Ingestion"]
        KAFKA[Apache Kafka\nBehavioral Event Stream\nTopic per workflow type]
        ENRICHER --> KAFKA
    end

    subgraph Baseline_Engine["Baseline Registry"]
        GOLDEN[Golden Run Curator\nHuman-approved traces]
        QDRANT[Qdrant Vector Store\nSemantic Baselines\nEmbedding clusters]
        TSDB[TimescaleDB\nStructural + Distributional\nBaseline Metrics]
        GOLDEN --> QDRANT
        GOLDEN --> TSDB
    end

    subgraph Drift_Detection_Workers["Drift Detection Workers"]
        STRUCT[Structural Analyzer\nTool sequence divergence\nStep order anomalies\nMarkov chain comparison]
        SEM[Semantic Analyzer\nCosine distance from\nbaseline embedding\nIntent drift scoring]
        DIST[Distributional Analyzer\nCUSUM / EWMA\nOutput distribution shift\nRetrieval quality decay]
    end

    subgraph Scoring_Engine["Unified Drift Scoring"]
        FUSE[Signal Fusion Layer\nWeighted composite\ndrift score per run]
        ALERT[Alert Router\nSeverity classification\nCooldown / dedup logic]
    end

    subgraph Explainability_Service["Explainability Service\n(On-Alert Only)"]
        LLM[LLM API\nGPT-4o / Claude\nDrift narrative generation]
        EXPLAIN[Explanation Cache\nRedis]
        LLM --> EXPLAIN
    end

    subgraph Control_Plane["Control Plane API"]
        API[FastAPI\nREST + WebSocket\nWorkflow config CRUD\nBaseline management]
        AUTH[Auth Middleware\nOIDC / SAML\nEnterprise SSO]
        API --> AUTH
    end

    subgraph Observability_UI["Dashboard & Integrations"]
        UI[React Dashboard\nDrift timelines\nTrace diffs\nWorkflow heatmaps]
        WEBHOOK[Outbound Webhooks\nPagerDuty / Slack\nJIRA / OpsGenie]
        PROM[Prometheus Exporter\nDrift scores as metrics\nExisting infra overlay]
    end

    A1 & A2 & A3 -->|auto-instrumented spans| SDK
    KAFKA -->|consume events| STRUCT
    KAFKA -->|consume events| SEM
    KAFKA -->|consume events| DIST

    STRUCT --> FUSE
    SEM --> FUSE
    DIST --> FUSE

    QDRANT -->|baseline embeddings| SEM
    TSDB -->|baseline distributions| DIST & STRUCT

    FUSE --> TSDB
    FUSE --> ALERT

    ALERT -->|on high severity| LLM
    ALERT --> WEBHOOK

    API --> QDRANT
    API --> TSDB
    API --> EXPLAIN

    UI -->|queries| API
    FUSE -->|drift metrics| PROM

    classDef external fill:#f5a623,stroke:#d4881a,color:#000
    classDef storage fill:#4a90d9,stroke:#2c6fad,color:#fff
    classDef worker fill:#7bc67e,stroke:#4a9b4e,color:#000
    classDef ui fill:#9b59b6,stroke:#7d3c98,color:#fff

    class KAFKA,QDRANT,TSDB,EXPLAIN storage
    class STRUCT,SEM,DIST,FUSE worker
    class UI,PROM,WEBHOOK ui
    class LLM external
```
