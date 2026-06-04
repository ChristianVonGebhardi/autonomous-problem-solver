from fastapi import APIRouter
from app.db.neo4j_client import neo4j_client
from app.db.qdrant_client import qdrant_client
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """System health check."""
    checks: dict = {}

    # Neo4j
    try:
        result = await neo4j_client.run_query("RETURN 1 AS ok")
        checks["neo4j"] = "ok" if result else "error"
    except Exception as e:
        checks["neo4j"] = f"error: {str(e)[:50]}"

    # Qdrant
    try:
        if qdrant_client.client:
            await qdrant_client.client.get_collections()
            checks["qdrant"] = "ok"
        else:
            checks["qdrant"] = "not connected"
    except Exception as e:
        checks["qdrant"] = f"error: {str(e)[:50]}"

    # Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:50]}"

    # PostgreSQL
    try:
        from app.db.postgres import engine
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {str(e)[:50]}"

    # LLM mode
    checks["llm"] = "openai" if settings.openai_api_key else "mock"
    checks["demo_mode"] = settings.demo_mode

    # Overall status: ok if neo4j+qdrant are up (the core stores)
    core_ok = all(
        checks.get(svc) == "ok"
        for svc in ("neo4j", "qdrant", "redis", "postgres")
    )
    overall = "ok" if core_ok else "degraded"

    return {
        "status": overall,
        "version": "1.0.0",
        "checks": checks,
    }