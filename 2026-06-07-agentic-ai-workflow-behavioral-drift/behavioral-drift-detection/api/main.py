"""
FastAPI control plane for the Behavioral Drift Detection Platform.

Endpoints:
  POST /api/v1/traces          — SDK trace ingestion
  GET  /api/v1/traces          — list traces
  GET  /api/v1/traces/{run_id} — trace detail + drift score
  
  POST /api/v1/workflows       — register workflow
  GET  /api/v1/workflows       — list workflows
  GET  /api/v1/workflows/{id}/summary — drift health summary
  
  POST /api/v1/baselines/{workflow_id} — approve golden run
  GET  /api/v1/baselines/{workflow_id} — list baselines
  
  GET  /api/v1/drift/timeseries/{workflow_id}
  GET  /api/v1/drift/alerts/{workflow_id}
  GET  /api/v1/drift/score/{run_id}
  GET  /api/v1/drift/latest/{workflow_id}
  
  WebSocket /ws/drift/{workflow_id} — real-time drift events
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api.config import settings
from api.database import engine, Base
from api.routes import traces, workflows, baselines, drift

logger = structlog.get_logger(__name__)

# WebSocket connection manager for real-time drift events
class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, workflow_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections.setdefault(workflow_id, []).append(websocket)

    def disconnect(self, workflow_id: str, websocket: WebSocket):
        if workflow_id in self._connections:
            self._connections[workflow_id].discard(websocket)
            try:
                self._connections[workflow_id].remove(websocket)
            except ValueError:
                pass

    async def broadcast(self, workflow_id: str, message: dict):
        """Broadcast a drift event to all connected dashboard clients."""
        dead = []
        for ws in self._connections.get(workflow_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._connections[workflow_id].remove(ws)
            except ValueError:
                pass


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (migrations handled by alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Try to create TimescaleDB hypertable if extension available
        try:
            await conn.execute(text(
                "SELECT create_hypertable('drift_scores', 'ingested_at', "
                "if_not_exists => TRUE)"
            ))
            logger.info("timescaledb_hypertable_created")
        except Exception as e:
            # TimescaleDB not available — regular PostgreSQL table still works
            logger.info("timescaledb_not_available", reason=str(e))
    
    logger.info("api_startup", version="0.1.0")
    yield
    logger.info("api_shutdown")


app = FastAPI(
    title="Behavioral Drift Detection Platform",
    description="Detects silent behavioral drift in agentic AI workflows",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(traces.router)
app.include_router(workflows.router)
app.include_router(baselines.router)
app.include_router(drift.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.websocket("/ws/drift/{workflow_id}")
async def drift_websocket(websocket: WebSocket, workflow_id: str):
    """
    Real-time drift event stream for the dashboard.
    
    Clients receive a JSON message whenever a new drift score is computed
    for the specified workflow.
    """
    await manager.connect(workflow_id, websocket)
    try:
        while True:
            # Keep connection alive — actual events are pushed from the worker
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(workflow_id, websocket)


# Make the connection manager available to workers
app.state.ws_manager = manager