# ARTIFACT 1: ARCHITECTURE.md

## Codebase Knowledge Intelligence Platform

### Solution Overview
A continuously-updated, AI-powered knowledge graph that mines git history, PRs, code comments, Slack threads, and architectural decision records (ADRs) to build a queryable, living intelligence layer over any codebase. Developers ask natural-language questions; the system retrieves contextually-grounded answers tied to specific files, commits, and decisions.

### Technology Choices & Rationale
- **Ingestion Workers (Python/asyncio):** Native git, GitHub/GitLab, and Slack API support; rich NLP ecosystem.
- **Graph Database (Neo4j):** Captures relationships between files, authors, decisions, PRs, and concepts that flat vector stores cannot — critical for architectural reasoning.
- **Vector Store (Qdrant):** Semantic similarity search over code chunks and documentation; complements Neo4j for hybrid retrieval.
- **LLM Layer (OpenAI GPT-4o / local Ollama fallback):** Synthesizes retrieved context into coherent explanations; RAG architecture prevents hallucination.
- **Embedding Pipeline (sentence-transformers + tree-sitter):** Language-agnostic code chunking with semantic boundaries.
- **API Layer (FastAPI):** Async, typed, easily extensible.
- **Frontend (Next.js + VS Code Extension):** Meets developers where they work.
- **Task Queue (Celery + Redis):** Manages continuous re-ingestion without blocking queries.
- **Deployment:** Kubernetes-compatible Docker Compose; self-hostable for enterprise data residency requirements.

### Known Constraints & Human Assistance Required
- **API Keys Needed:** OpenAI API, GitHub/GitLab OAuth apps, Slack app credentials.
- **Proprietary integrations:** Confluence, Jira, Linear require per-instance OAuth setup.
- **LLM cost management:** Production deployments need rate-limit budgeting.
- **Cold start:** Initial full-repo ingestion may take hours for large monorepos.

## Architecture Diagram

```mermaid
flowchart TB
    subgraph Sources["Data Sources"]
        GIT[Git Repository\nCommits & Blame]
        PR[GitHub / GitLab\nPRs & Reviews]
        SLACK[Slack\nThreads & Channels]
        DOCS[Confluence / Notion\nADRs & Wikis]
        JIRA[Jira / Linear\nTickets & Epics]
    end

    subgraph Ingestion["Ingestion Layer (Python/Celery + Redis)"]
        GIT_W[Git Ingestion Worker]
        PR_W[PR & Review Worker]
        COMM_W[Communication Worker]
        DOC_W[Docs & ADR Worker]
        CHUNK[Code Chunker\ntree-sitter]
        EMBED[Embedding Service\nsentence-transformers]
    end

    subgraph Storage["Knowledge Storage"]
        NEO[Neo4j\nKnowledge Graph\nfiles · authors · decisions · PRs]
        VEC[Qdrant\nVector Store\nsemantic chunks]
        PG[(PostgreSQL\nMetadata & Audit)]
    end

    subgraph Query["Query & Reasoning Layer"]
        API[FastAPI\nQuery API]
        HYBRID[Hybrid Retriever\ngraph traversal + vector search]
        LLM[LLM Synthesizer\nGPT-4o / Ollama fallback]
        CACHE[Redis\nResponse Cache]
    end

    subgraph Interface["Developer Interfaces"]
        VSCE[VS Code Extension\ninline Q&A]
        WEB[Next.js Web App\nonboarding dashboard]
        BOT[Slack Bot\n/ask-codebase]
        CICD[CI/CD Hook\nPR context annotation]
    end

    subgraph Maintenance["Continuous Maintenance"]
        SCHED[Scheduler\ndelta re-ingestion]
        DECAY[Knowledge Decay Detector\nstale node alerting]
        GRAPH_VIZ[Graph Visualizer\narchitecture map]
    end

    GIT --> GIT_W
    PR --> PR_W
    SLACK --> COMM_W
    DOCS --> DOC_W
    JIRA --> DOC_W

    GIT_W --> CHUNK
    PR_W --> EMBED
    COMM_W --> EMBED
    DOC_W --> EMBED
    CHUNK --> EMBED

    EMBED --> VEC
    GIT_W --> NEO
    PR_W --> NEO
    COMM_W --> NEO
    DOC_W --> NEO
    NEO <-->|cross-link\nnodes| VEC
    NEO --> PG
    VEC --> PG

    VSCE --> API
    WEB --> API
    BOT --> API
    CICD --> API

    API --> CACHE
    CACHE -->|miss| HYBRID
    HYBRID --> NEO
    HYBRID --> VEC
    HYBRID --> LLM
    LLM --> API

    SCHED --> GIT_W
    SCHED --> PR_W
    DECAY --> NEO
    DECAY --> WEB
    GRAPH_VIZ --> NEO
    GRAPH_VIZ --> WEB
```
