from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, DateTime, JSON, Integer, Text, Boolean
from sqlalchemy.sql import func
import uuid

from app.config import settings

# Convert sync URL to async
db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    repo_path = Column(String)
    repo_url = Column(String)
    status = Column(String, default="pending")  # pending, ingesting, ready, error
    last_ingested_at = Column(DateTime(timezone=True))
    file_count = Column(Integer, default=0)
    commit_count = Column(Integer, default=0)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    repo_name = Column(String, nullable=False)
    job_type = Column(String)  # git, github, slack, docs
    status = Column(String, default="pending")
    celery_task_id = Column(String)
    progress = Column(Integer, default=0)
    error_message = Column(Text)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    repo_name = Column(String)
    question = Column(Text, nullable=False)
    answer = Column(Text)
    sources_count = Column(Integer, default=0)
    latency_ms = Column(Integer)
    model_used = Column(String)
    cached = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency for getting DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()