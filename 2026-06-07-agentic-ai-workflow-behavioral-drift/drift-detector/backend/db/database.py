"""
Database connection and session management.
Supports both PostgreSQL/TimescaleDB (production) and SQLite (fallback/testing).
"""

import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

# Detect database URL — fall back to SQLite for development without Docker
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    # SQLite fallback for development
    DATABASE_URL = "sqlite+aiosqlite:///./drift_detector.db"
    logger.info("DATABASE_URL not set — using SQLite fallback")
elif DATABASE_URL.startswith("postgresql://"):
    # Convert to asyncpg
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

is_sqlite = "sqlite" in DATABASE_URL

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if is_sqlite else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency — yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()