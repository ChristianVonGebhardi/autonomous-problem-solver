from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


class Base(DeclarativeBase):
    pass


# Async engine for FastAPI
async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine for Celery workers
def get_sync_url():
    url = settings.database_url
    # Convert asyncpg to psycopg2 if needed
    if "asyncpg" in url:
        url = url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    return url


sync_engine = create_engine(
    get_sync_url(),
    pool_size=5,
    max_overflow=10,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()