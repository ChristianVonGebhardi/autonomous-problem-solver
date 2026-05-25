import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.database import engine, get_db
from app.models import Base
from app.websocket_manager import manager
from app.routers import auth, contracts, messages, violations, change_orders, dashboard

settings = get_settings()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    # Create upload directories
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(f"{settings.upload_dir}/contracts").mkdir(parents=True, exist_ok=True)
    Path(f"{settings.upload_dir}/change_orders").mkdir(parents=True, exist_ok=True)
    
    # Create tables and pgvector extension
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("application_started", env=settings.app_env)
    
    yield
    
    await engine.dispose()
    logger.info("application_stopped")


app = FastAPI(
    title="ScopeGuard AI",
    description="AI-powered scope creep detection for freelancers",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(contracts.router)
app.include_router(messages.router)
app.include_router(violations.router)
app.include_router(change_orders.router)
app.include_router(dashboard.router)


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for real-time notifications."""
    await manager.connect(websocket, user_id)
    logger.info("ws_client_connected", user_id=user_id)
    
    # Start Redis subscriber in background if available
    redis_task = None
    try:
        redis_task = asyncio.create_task(
            _redis_subscriber(user_id, websocket)
        )
    except Exception:
        pass
    
    try:
        while True:
            # Keep connection alive, handle ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        if redis_task:
            redis_task.cancel()
        logger.info("ws_client_disconnected", user_id=user_id)


async def _redis_subscriber(user_id: str, websocket: WebSocket):
    """Subscribe to Redis pub/sub for violation notifications."""
    try:
        import redis.asyncio as aioredis
        r = await aioredis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe("violations")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    if data.get("user_id") == user_id:
                        await websocket.send_text(json.dumps(data))
                except Exception:
                    pass
    except Exception as e:
        logger.warning("redis_subscriber_error", error=str(e))