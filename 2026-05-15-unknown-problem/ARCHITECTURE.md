# ARTIFACT 1: ARCHITECTURE.md

## Solution Overview
A desktop-native application built with Tauri (Rust backend + web frontend) providing a local-first, privacy-focused LLM interaction environment. The architecture prioritizes zero-latency UI, offline capability, and secure credential management while supporting multiple LLM providers through a unified abstraction layer.

## Technology Choices

**Core Framework: Tauri v2**
- Rust backend provides memory safety, performance, and cross-platform compilation
- Web frontend (React + TypeScript) enables rapid UI development with rich component ecosystems
- 600KB binary overhead vs 150MB+ Electron makes distribution feasible
- Native OS integration for file system access, tray icons, and system notifications

**LLM Integration: Custom Rust Provider Abstraction**
- Unified async trait for OpenAI, Anthropic, Google, local models (Ollama/llama.cpp)
- HTTP/2 streaming via reqwest for SSE responses
- Local model support through FFI bindings or subprocess management
- No MCP needed—direct HTTP client interaction is simpler and faster

**State Management**
- Frontend: Zustand (lightweight React state) + TanStack Query for async data
- Backend: In-memory state with SQLite persistence (conversations, settings, API keys)
- Encrypted credential storage using OS keychain (Windows Credential Manager, macOS Keychain, Linux Secret Service)

**Data Flow**
Frontend → Tauri IPC → Rust command handlers → LLM provider abstraction → HTTP API / Local process → Stream responses via Tauri events → Frontend updates

## Deployment Target
Single-binary executables for Windows (x64), macOS (Intel + Apple Silicon), Linux (x64, AppImage). Auto-updates via Tauri's built-in updater with GitHub Releases.

## Human-Assistance Requirements
- API keys from users for cloud LLM providers (OpenAI, Anthropic, etc.)
- Code signing certificates for macOS notarization and Windows SmartScreen bypass
- CI/CD configuration for cross-platform builds (GitHub Actions with platform-specific runners)

## Architecture Diagram

```mermaid
graph TB
    subgraph "Frontend (React + TypeScript)"
        A[UI Components]
        B[Zustand State Store]
        C[TanStack Query]
    end
    
    subgraph "Tauri IPC Layer"
        D[Commands API]
        E[Event Emitter]
    end
    
    subgraph "Rust Backend"
        F[Command Handlers]
        G[LLM Provider Abstraction]
        H[Config Manager]
        I[Credential Store]
        J[SQLite Database]
    end
    
    subgraph "LLM Providers"
        K[OpenAI API]
        L[Anthropic API]
        M[Google Gemini API]
        N[Local Ollama/llama.cpp]
    end
    
    subgraph "OS Integration"
        O[System Keychain]
        P[File System]
        Q[System Tray]
    end
    
    A -->|User Actions| D
    D --> F
    F --> G
    F --> H
    F --> I
    F --> J
    
    G -->|HTTP/2 SSE| K
    G -->|HTTP/2 SSE| L
    G -->|HTTP/2 SSE| M
    G -->|Subprocess/FFI| N
    
    G -->|Stream Chunks| E
    E -->|Event Subscription| C
    C --> B
    B --> A
    
    I <-->|Encrypted Storage| O
    F <-->|Read/Write| P
    F --> Q
    
    H --> J
    
    style A fill:#e1f5ff
    style F fill:#fff4e1
    style G fill:#ffe1e1
    style J fill:#e1ffe1
```

