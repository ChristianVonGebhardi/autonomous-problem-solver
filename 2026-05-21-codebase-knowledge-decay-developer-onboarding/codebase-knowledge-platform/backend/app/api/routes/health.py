from fastapi import APIRouter
from app.db.neo4j_client import neo4j_client
from app.db.qdrant_client import qdrant_client
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """System health check."""
    checks = {}

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

    # LLM mode
    checks["llm"] = "openai" if settings.openai_api_key else "mock"
    checks["demo_mode"] = settings.demo_mode

    overall = "ok" if all("ok" in v for v in checks.values() if isinstance(v, str)) else "degraded"

    return {
        "status": overall,
        "version": "1.0.0",
        "checks": checks,
    }