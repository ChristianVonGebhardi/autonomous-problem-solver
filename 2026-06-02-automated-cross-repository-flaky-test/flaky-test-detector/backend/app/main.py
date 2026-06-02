"""
Main FastAPI application entry point.
"""
import asyncio
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.init_db import init_database
from app.api import events, flaky_tests, analyses, fixes, dashboard, websocket

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    logger.info("starting_application")
    try:
        init_database()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
    yield
    logger.info("shutting_down")


app = FastAPI(
    title="Flaky Test Root-Cause Attribution API",
    description=(
        "Automated detection, classification, and self-healing for flaky CI/CD tests. "
        "Ingests test execution telemetry, classifies root causes (timing, concurrency, "
        "environment, state leakage), and proposes targeted code-level fixes."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(events.router, prefix="/api/v1", tags=["Ingestion"])
app.include_router(flaky_tests.router, prefix="/api/v1", tags=["Flaky Tests"])
app.include_router(analyses.router, prefix="/api/v1", tags=["Analyses"])
app.include_router(fixes.router, prefix="/api/v1", tags=["Fix Proposals"])
app.include_router(dashboard.router, prefix="/api/v1", tags=["Dashboard"])
app.include_router(websocket.router, tags=["WebSocket"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/")
async def root():
    return {
        "name": "Flaky Test Detector",
        "docs": "/docs",
        "health": "/health",
    }