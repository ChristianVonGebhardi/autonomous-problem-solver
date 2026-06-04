import time
import uuid
import json
import structlog
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.postgres import get_db, QueryLog, Repository
from app.services.retrieval_service import hybrid_retriever
from app.services.llm_service import llm_service
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()

# Lazy Redis client
_redis_client = None


async def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
            await client.ping()
            _redis_client = client
        except Exception as e:
            logger.debug("Redis not available for caching", error=str(e))
            _redis_client = False  # Mark as unavailable
    return _redis_client if _redis_client else None


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    repo_name: Optional[str] = Field(None, description="Filter to specific repo")
    top_k: int = Field(default=8, ge=1, le=20)


class QueryResponse(BaseModel):
    answer: str
    sources: List[dict]
    model_used: str
    latency_ms: int
    cached: bool
    context_chunks_used: int
    repo_name: Optional[str]


@router.post("", response_model=QueryResponse)
async def query_codebase(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Query the codebase knowledge base using natural language."""
    start_time = time.time()

    # Check Redis cache
    cache_key = f"query:{request.repo_name}:{hash(request.question)}"
    redis = await _get_redis()

    if redis:
        try:
            cached_result = await redis.get(cache_key)
            if cached_result:
                result = json.loads(cached_result)
                result["cached"] = True
                result["latency_ms"] = int((time.time() - start_time) * 1000)
                return QueryResponse(**result)
        except Exception as e:
            logger.debug("Cache read error", error=str(e))

    # Validate repo exists if specified
    if request.repo_name:
        result = await db.execute(
            select(Repository).where(Repository.name == request.repo_name)
        )
        repo = result.scalar_one_or_none()
        if not repo:
            raise HTTPException(
                status_code=404,
                detail=f"Repository '{request.repo_name}' not found. Please ingest it first.",
            )
        if repo.status not in ("ready", "ingesting"):
            raise HTTPException(
                status_code=400,
                detail=f"Repository '{request.repo_name}' is not ready (status: {repo.status})",
            )

    # Hybrid retrieval: vector search + graph traversal
    retrieval_result = await hybrid_retriever.retrieve(
        question=request.question,
        repo_name=request.repo_name or "",
        top_k=request.top_k,
    )

    chunks = retrieval_result["chunks"]
    graph_context = retrieval_result["graph_context"]

    # LLM synthesis
    llm_result = await llm_service.answer_question(
        question=request.question,
        context_chunks=chunks,
        graph_context=graph_context,
        repo_name=request.repo_name or "all repositories",
    )

    latency_ms = int((time.time() - start_time) * 1000)

    response_data = {
        "answer": llm_result["answer"],
        "sources": llm_result["sources"],
        "model_used": llm_result["model_used"],
        "latency_ms": latency_ms,
        "cached": False,
        "context_chunks_used": llm_result["context_chunks_used"],
        "repo_name": request.repo_name,
    }

    # Persist query log
    query_log = QueryLog(
        id=str(uuid.uuid4()),
        repo_name=request.repo_name,
        question=request.question,
        answer=(llm_result["answer"] or "")[:1000],
        sources_count=len(llm_result["sources"]),
        latency_ms=latency_ms,
        model_used=llm_result["model_used"],
        cached=False,
    )
    db.add(query_log)
    try:
        await db.commit()
    except Exception as e:
        logger.warning("Failed to persist query log", error=str(e))
        await db.rollback()

    # Cache result (TTL: 10 minutes)
    if redis:
        try:
            await redis.setex(cache_key, 600, json.dumps(response_data))
        except Exception as e:
            logger.debug("Cache write error", error=str(e))

    return QueryResponse(**response_data)


@router.get("/history")
async def get_query_history(
    repo_name: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get recent query history."""
    stmt = select(QueryLog).order_by(QueryLog.created_at.desc()).limit(limit)
    if repo_name:
        stmt = stmt.where(QueryLog.repo_name == repo_name)

    result = await db.execute(stmt)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "question": log.question,
            "answer_preview": (log.answer or "")[:200],
            "repo_name": log.repo_name,
            "latency_ms": log.latency_ms,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]