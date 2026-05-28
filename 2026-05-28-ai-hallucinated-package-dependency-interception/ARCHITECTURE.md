The solution is **GuardRail** — a multi-layer, open-source supply-chain interception platform that validates AI-generated package dependencies at three enforcement points: IDE (real-time, pre-acceptance), package-manager proxy (pre-install), and CI/CD gate (pre-merge). The architecture is deliberately polyglot-hostile: a single Rust core library handles all validation logic for performance and memory safety, surfaced through thin language-specific bindings (Python, Node.js, VS Code Extension API). Rust is chosen because package-manager hooks run synchronously in hot paths where latency is felt immediately, and supply-chain tooling itself must be trustworthy.

The central **Validation Engine** runs three checks in parallel: (1) Registry Existence — live HTTP calls to PyPI JSON API, npm registry, crates.io, Go module proxy, Maven Central; (2) Typosquatting/Slopsquatting Heuristics — edit-distance, phonetic similarity, and n-gram language model scoring against known-good package corpuses to flag names with AI-generation fingerprints; (3) Package Reputation — download counts, publish date, maintainer count, and GitHub stars fetched via registry metadata. A local SQLite cache (with 15-minute TTL) prevents redundant API calls during rapid edit cycles.

The **IDE Plugin** (VS Code / JetBrains) hooks into document save and AI completion acceptance events, calling the Rust engine via Node.js N-API or JVM JNI bindings, surfacing inline diagnostics before the developer moves on. The **Package Manager Proxy** wraps pip, npm, cargo, and go with shim scripts that invoke the engine pre-install, blocking on policy violations. The **CI/CD Gate** ships as a GitHub Actions action, GitLab CI component, and generic CLI — scanning manifest files (requirements.txt, package.json, Cargo.toml, go.mod) against the engine with a structured JSON report and configurable fail policy.

A lightweight **Policy Server** (Go HTTP service, deployable as a single binary or container) lets enterprise teams centralize allow-lists, block-lists, and risk thresholds, with SQLite for small teams and PostgreSQL for enterprises. All components phone home to the policy server only when explicitly configured; fully air-gapped operation is supported.

Human assistance is required for: npm/PyPI API keys for higher rate limits, GitHub App credentials for PR decoration, and optional LLM scoring API keys (for name-pattern analysis) if teams want the cloud-enhanced tier.

## Architecture Diagram

```mermaid
flowchart TD
    subgraph Developer_Environment["Developer Environment"]
        IDE["IDE Plugin\n(VS Code / JetBrains)"]
        AI_Assistant["AI Coding Assistant\n(Copilot / Cursor / Claude)"]
        PM_SHIM["Package Manager Shim\n(pip / npm / cargo / go wrap)"]
        MANIFEST["Manifest Files\n(requirements.txt / package.json\nCargo.toml / go.mod)"]
    end

    subgraph GuardRail_Core["GuardRail Core (Rust Library)"]
        VALIDATOR["Validation Engine\nOrchestrator"]
        REG_CHECK["Registry Existence\nChecker"]
        HEURISTIC["Slopsquatting Heuristic\nEngine (edit-distance,\nn-gram LM scoring)"]
        REPUTATION["Package Reputation\nScorer (age, downloads,\nmaintainers)"]
        CACHE["Local SQLite Cache\n(15-min TTL)"]
    end

    subgraph External_Registries["External Package Registries"]
        PYPI["PyPI JSON API"]
        NPM["npm Registry API"]
        CRATES["crates.io API"]
        GOMOD["Go Module Proxy"]
        MAVEN["Maven Central API"]
    end

    subgraph Policy_Server["Policy Server (Go Binary / Container)"]
        POLICY_API["Policy REST API"]
        ALLOWLIST["Allow / Block Lists"]
        RISK_CFG["Risk Thresholds\n& Team Policy"]
        POLICY_DB["SQLite / PostgreSQL"]
    end

    subgraph CICD_Gate["CI/CD Gate"]
        GH_ACTION["GitHub Actions\nAction"]
        GL_COMPONENT["GitLab CI\nComponent"]
        CLI["Generic CLI\n(guardrail scan)"]
        REPORT["JSON / SARIF\nReport Output"]
    end

    subgraph Notification["Developer Feedback"]
        INLINE_WARN["Inline IDE Warning\n/ Diagnostic"]
        BLOCK_INSTALL["Blocked Install\n+ Remediation Hint"]
        PR_COMMENT["PR Comment /\nCheck Failure"]
    end

    AI_Assistant -- "suggests import / dependency" --> IDE
    IDE -- "on save / completion accept" --> VALIDATOR
    PM_SHIM -- "pre-install hook" --> VALIDATOR
    CLI -- "scans manifest" --> VALIDATOR
    GH_ACTION -- "triggers on push/PR" --> CLI
    GL_COMPONENT -- "triggers on push/MR" --> CLI
    MANIFEST -- "parsed by" --> CLI

    VALIDATOR --> REG_CHECK
    VALIDATOR --> HEURISTIC
    VALIDATOR --> REPUTATION
    REG_CHECK <--> CACHE
    HEURISTIC <--> CACHE
    REPUTATION <--> CACHE

    CACHE -- "miss: fetch" --> PYPI
    CACHE -- "miss: fetch" --> NPM
    CACHE -- "miss: fetch" --> CRATES
    CACHE -- "miss: fetch" --> GOMOD
    CACHE -- "miss: fetch" --> MAVEN

    VALIDATOR -- "optional: check policy" --> POLICY_API
    POLICY_API --- ALLOWLIST
    POLICY_API --- RISK_CFG
    POLICY_API --- POLICY_DB

    VALIDATOR -- "WARN / BLOCK result" --> IDE
    VALIDATOR -- "WARN / BLOCK result" --> PM_SHIM
    VALIDATOR -- "structured result" --> REPORT

    IDE --> INLINE_WARN
    PM_SHIM --> BLOCK_INSTALL
    REPORT --> PR_COMMENT

    style GuardRail_Core fill:#1e3a5f,color:#fff
    style Developer_Environment fill:#1a3a2a,color:#fff
    style CICD_Gate fill:#3a2a1a,color:#fff
    style Policy_Server fill:#2a1a3a,color:#fff
    style External_Registries fill:#1a2a3a,color:#fff
    style Notification fill:#3a1a1a,color:#fff
```
