The system is a SaaS web application that ingests signed contracts, monitors communication channels in real time, and uses an LLM pipeline to detect scope creep and auto-generate change orders. The core technology stack is: **Python (FastAPI)** for backend services due to its async performance and rich ML ecosystem; **React + TypeScript** for the frontend because of strong typing and component reuse; **PostgreSQL** with **pgvector** extension as the primary data store, enabling both relational contract metadata and semantic vector search over contract clauses without a separate vector database; **Redis** for job queues (via Celery) and caching; and **OpenAI GPT-4o** as the LLM backbone for contract parsing, message analysis, and change-order drafting, chosen because it offers the best instruction-following and document comprehension at commercially viable latency.

The architecture has five major components: (1) **Ingestion Service** — PDF/DOCX contract parser using PyMuPDF + Unstructured.io that chunks contract text, embeds chunks with `text-embedding-3-large`, and stores them in pgvector; (2) **Integration Hub** — OAuth connectors for Gmail, Outlook, Slack, and Linear that stream incoming client messages via webhooks into a Redis queue; (3) **Scope Analysis Engine** — a Celery worker that retrieves relevant contract chunks via cosine similarity, then calls GPT-4o with a structured prompt comparing the message against scope boundaries, returning a violation score, specific clause citations, and a severity label; (4) **Change Order Generator** — a secondary LLM call that drafts a professional change-order document using the freelancer's stored rate card and the detected out-of-scope work; (5) **Notification + Dashboard** — a React SPA that displays real-time alerts via WebSockets (Socket.io), lets users review/approve/send change orders, and shows a monthly "recovered revenue" metric.

Data flows: raw message → Redis queue → Scope Analysis Engine (vector retrieval + LLM) → violation record in Postgres → WebSocket push to dashboard → user approves change order → PDF rendered and sent via SendGrid. Deployment targets AWS on ECS Fargate (containerized services) with RDS Postgres, ElastiCache Redis, and S3 for contract storage, keeping infrastructure serverless-adjacent and cost-proportional to usage. Human-assisted requirements include: OpenAI API key + billing, OAuth app credentials for each communication platform (Google, Microsoft, Slack), SendGrid account for email delivery, and Stripe integration for SaaS billing.

## Architecture Diagram

```mermaid
flowchart TD
    subgraph Client["Client Layer"]
        UI["React + TypeScript SPA\n(Dashboard / Alerts / Change Orders)"]
        WS["WebSocket Client\n(Socket.io)"]
    end

    subgraph Integrations["Communication Integrations"]
        GH["Gmail / Outlook\n(OAuth + Webhooks)"]
        SL["Slack\n(Events API)"]
        LN["Linear / Asana\n(Webhooks)"]
    end

    subgraph API["API Layer (FastAPI)"]
        GW["API Gateway\n(Auth / Rate Limit)"]
        WSS["WebSocket Server\n(Socket.io)"]
        CO["Change Order API"]
    end

    subgraph Ingestion["Contract Ingestion Service"]
        UP["File Upload Handler\n(PDF / DOCX)"]
        PR["Document Parser\n(PyMuPDF + Unstructured.io)"]
        EM["Embedder\n(text-embedding-3-large)"]
    end

    subgraph Queue["Async Processing (Redis + Celery)"]
        MQ["Message Queue\n(Redis)"]
        SAW["Scope Analysis Worker\n(Celery)"]
        COW["Change Order Worker\n(Celery)"]
    end

    subgraph AI["AI Layer"]
        VR["Vector Retrieval\n(pgvector cosine similarity)"]
        LLM1["GPT-4o\nScope Analysis + Clause Citation"]
        LLM2["GPT-4o\nChange Order Drafting"]
    end

    subgraph Storage["Data Layer"]
        PG[("PostgreSQL + pgvector\n(contracts, clauses,\nviolations, users)")]
        S3["S3\n(Raw contract files\nChange order PDFs)"]
        RC[("Redis Cache\n(sessions, rate cards)")]
    end

    subgraph Notify["Notification Layer"]
        SG["SendGrid\n(Email delivery)"]
        PDF["PDF Renderer\n(WeasyPrint)"]
    end

    GH -->|"webhook events"| MQ
    SL -->|"webhook events"| MQ
    LN -->|"webhook events"| MQ

    UI -->|"REST / HTTPS"| GW
    UI <-->|"real-time alerts"| WS
    WS <-->|"WebSocket"| WSS

    GW --> UP
    UP --> PR
    PR --> EM
    EM -->|"store chunks + vectors"| PG
    UP -->|"store raw file"| S3

    MQ -->|"dequeue message"| SAW
    SAW --> VR
    VR -->|"query similar clauses"| PG
    VR -->|"top-k chunks"| LLM1
    LLM1 -->|"violation record + severity"| PG
    LLM1 -->|"trigger if violation"| COW
    COW --> LLM2
    LLM2 -->|"draft change order"| PG
    LLM2 -->|"generate PDF"| PDF
    PDF -->|"store PDF"| S3

    PG -->|"violation event"| WSS
    WSS -->|"push alert"| WS

    GW --> CO
    CO -->|"approve + send"| SG
    CO -->|"fetch PDF"| S3

    SAW <-->|"cache rate cards"| RC
    GW <-->|"session cache"| RC
```
