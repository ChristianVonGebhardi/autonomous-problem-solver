"""
Database initialization script.

Creates all tables and optionally sets up TimescaleDB hypertable on drift_scores.
Run once before starting the API server.

Usage:
    python -m scripts.init_db
"""

from __future__ import annotations

import asyncio
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from api.config import settings
from api.database import Base, _make_async_url
from api.models import *  # noqa: F401,F403 — import all models so Base knows them

logger = structlog.get_logger(__name__)


async def init_db():
    engine = create_async_engine(_make_async_url(settings.database_url), echo=True)
    
    logger.info("creating_tables", database_url=settings.database_url)
    
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("tables_created")
        
        # Try to enable TimescaleDB
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
            await conn.execute(text(
                "SELECT create_hypertable('drift_scores', 'ingested_at', "
                "if_not_exists => TRUE)"
            ))
            logger.info("timescaledb_hypertable_created", table="drift_scores")
        except Exception as exc:
            logger.info(
                "timescaledb_not_available",
                message="Using standard PostgreSQL time-series queries",
                detail=str(exc),
            )
    
    await engine.dispose()
    logger.info("db_init_complete")


if __name__ == "__main__":
    asyncio.run(init_db())