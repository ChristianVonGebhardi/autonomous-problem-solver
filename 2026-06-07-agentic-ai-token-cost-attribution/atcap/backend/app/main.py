"""ATCAP — AI Token Cost Attribution Platform — FastAPI application."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.init_db import init_db
from app.api.v1 import events, costs, budgets, roi, pricing, alerts
from app.services.cost_processor import (
    compute_windowed_aggregates,
    evaluate_budget_policies,
    compute_roi_records,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def background_processor():
    """Periodic background task for cost aggregation and policy evaluation."""
    while True:
        try:
            await compute_windowed_aggregates(window_minutes=15)
            await evaluate_budget_policies()
        except Exception as e:
            logger.error(f"Background processor error: {e}")
        await asyncio.sleep(60)  # Run every 60s


async def roi_processor():
    """Periodic ROI computation (less frequent)."""
    while True:
        try:
            await compute_roi_records()
        except Exception as e:
            logger.error(f"ROI processor error: {e}")
        await asyncio.sleep(300)  # Run every 5 min


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Initializing ATCAP database...")
    await init_db()
    logger.info("Starting background processors...")
    bg_task = asyncio.create_task(background_processor())
    roi_task = asyncio.create_task(roi_processor())
    yield
    bg_task.cancel()
    roi_task.cancel()
    logger.info("ATCAP shutdown complete")


app = FastAPI(
    title="ATCAP — AI Token Cost Attribution Platform",
    description=(
        "Purpose-built instrumentation and analytics for AI token cost attribution, "
        "budget management, and business-value ROI correlation."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"
app.include_router(events.router, prefix=PREFIX, tags=["Events"])
app.include_router(costs.router, prefix=PREFIX, tags=["Costs"])
app.include_router(budgets.router, prefix=PREFIX, tags=["Budgets"])
app.include_router(alerts.router, prefix=PREFIX, tags=["Alerts"])
app.include_router(roi.router, prefix=PREFIX, tags=["ROI"])
app.include_router(pricing.router, prefix=PREFIX, tags=["Pricing"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "atcap"}


@app.get("/")
async def root():
    return {
        "service": "ATCAP",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }