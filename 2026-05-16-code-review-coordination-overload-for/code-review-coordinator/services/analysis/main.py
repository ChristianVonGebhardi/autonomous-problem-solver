import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Optional, List
import numpy as np
import nats
import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from complexity_scorer import PRComplexityScorer

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="PR Analysis Engine", version="1.0.0")

# Global connections
db_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[aioredis.Redis] = None
nats_client = None
js = None
scorer = PRComplexityScorer()


class PRAnalysisRequest(BaseModel):
    pr_id: str
    external_id: str
    repo: str
    lines_added: int = 0
    lines_deleted: int = 0
    files_changed: int = 0
    title: str = ""
    author: str = ""
    action: str = "opened"


class PRAnalysisResult(BaseModel):
    pr_id: str
    complexity_score: float
    risk_score: float
    estimated_review_minutes: int
    factors: dict
    recommended_reviewers_count: int


@app.on_event("startup")
async def startup():
    global db_pool, redis_client, nats_client, js

    # Connect to PostgreSQL
    for attempt in range(15):
        try:
            db_pool = await asyncpg.create_pool(
                dsn=os.getenv("POSTGRES_DSN", "postgresql://coordinator:coordinator_secret@localhost:5432/crcoordinator"),
                min_size=2,
                max_size=10
            )
            logger.info("Connected to PostgreSQL")
            break
        except Exception as e:
            logger.warning(f"PostgreSQL connection attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2)

    # Connect to Redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("Connected to Redis")

    # Connect to NATS
    for attempt in range(15):
        try:
            nats_client = await nats.connect(
                os.getenv("NATS_URL", "nats://localhost:4222")
            )
            js = nats_client.jetstream()
            logger.info("Connected to NATS JetStream")
            break
        except Exception as e:
            logger.warning(f"NATS connection attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2)

    # Start background subscriber
    asyncio.create_task(subscribe_pr_events())
    logger.info("Analysis engine started")


@app.on_event("shutdown")
async def shutdown():
    if nats_client:
        await nats_client.close()
    if db_pool:
        await db_pool.close()


async def subscribe_pr_events():
    """Subscribe to NATS for new PR events and analyze them."""
    if not js:
        logger.error("JetStream not available")
        return

    try:
        # Create consumer
        await js.subscribe(
            "pr.events.new",
            durable="analysis-worker",
            cb=handle_pr_event,
            stream="PR_EVENTS"
        )
        logger.info("Subscribed to pr.events.new")
    except Exception as e:
        logger.error(f"Failed to subscribe: {e}")


async def handle_pr_event(msg):
    """Handle incoming PR event from NATS."""
    try:
        data = json.loads(msg.data.decode())
        logger.info(f"Analyzing PR: {data.get('pr_id')}")

        req = PRAnalysisRequest(
            pr_id=data["pr_id"],
            external_id=data.get("external_id", ""),
            repo=data.get("repo", ""),
            lines_added=data.get("lines_added", 0),
            lines_deleted=data.get("lines_deleted", 0),
            files_changed=data.get("files_changed", 0),
            title=data.get("title", ""),
            author=data.get("author", ""),
            action=data.get("action", "opened"),
        )

        result = await analyze_pr(req)

        # Publish result for routing
        await js.publish(
            "pr.analyzed.ready",
            json.dumps({
                "pr_id": result.pr_id,
                "complexity_score": result.complexity_score,
                "risk_score": result.risk_score,
                "estimated_review_minutes": result.estimated_review_minutes,
                "recommended_reviewers_count": result.recommended_reviewers_count,
                "factors": result.factors,
            }).encode()
        )

        await msg.ack()
    except Exception as e:
        logger.error(f"Error handling PR event: {e}")
        await msg.nak()


async def analyze_pr(req: PRAnalysisRequest) -> PRAnalysisResult:
    """Core analysis logic."""
    # Get historical data for this author
    author_history = await get_author_history(req.author)

    # Score complexity
    complexity_score, factors = scorer.score(
        lines_added=req.lines_added,
        lines_deleted=req.lines_deleted,
        files_changed=req.files_changed,
        title=req.title,
        author_pr_count=author_history.get("pr_count", 0),
        author_avg_complexity=author_history.get("avg_complexity", 5.0),
    )

    # Risk score (security-sensitive keywords, large changes, etc.)
    risk_score = scorer.risk_score(
        lines_added=req.lines_added,
        files_changed=req.files_changed,
        title=req.title,
        repo=req.repo,
    )

    # Estimated review time (minutes)
    estimated_minutes = scorer.estimate_review_time(
        complexity_score=complexity_score,
        lines_added=req.lines_added,
        lines_deleted=req.lines_deleted,
    )

    # How many reviewers needed
    recommended_reviewers = 1
    if complexity_score > 7.0 or risk_score > 7.0:
        recommended_reviewers = 2
    if complexity_score > 9.0:
        recommended_reviewers = 3

    # Persist analysis results
    await persist_analysis(req.pr_id, complexity_score, risk_score, estimated_minutes, factors)

    return PRAnalysisResult(
        pr_id=req.pr_id,
        complexity_score=round(complexity_score, 2),
        risk_score=round(risk_score, 2),
        estimated_review_minutes=estimated_minutes,
        factors=factors,
        recommended_reviewers_count=recommended_reviewers,
    )


async def get_author_history(username: str) -> dict:
    """Fetch historical data for PR author."""
    if not db_pool:
        return {}
    try:
        row = await db_pool.fetchrow("""
            SELECT 
                COUNT(*) as pr_count,
                AVG(complexity_score) as avg_complexity
            FROM pull_requests
            WHERE author_username = $1
              AND complexity_score IS NOT NULL
        """, username)
        if row:
            return {
                "pr_count": row["pr_count"] or 0,
                "avg_complexity": float(row["avg_complexity"] or 5.0),
            }
    except Exception as e:
        logger.warning(f"Failed to get author history: {e}")
    return {}


async def persist_analysis(pr_id: str, complexity: float, risk: float,
                            est_minutes: int, factors: dict):
    """Save analysis results to DB and Redis."""
    if db_pool:
        try:
            await db_pool.execute("""
                UPDATE pull_requests
                SET complexity_score = $1, risk_score = $2, 
                    estimated_review_minutes = $3, updated_at = NOW()
                WHERE id = $4
            """, complexity, risk, est_minutes, pr_id)

            # Store individual metrics
            for metric_name, metric_value in factors.items():
                await db_pool.execute("""
                    INSERT INTO pr_metrics (pr_id, metric_name, metric_value)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                """, pr_id, metric_name, float(metric_value))
        except Exception as e:
            logger.error(f"Failed to persist analysis: {e}")

    if redis_client:
        try:
            await redis_client.hset(f"pr:analysis:{pr_id}", mapping={
                "complexity_score": str(complexity),
                "risk_score": str(risk),
                "estimated_review_minutes": str(est_minutes),
            })
            await redis_client.expire(f"pr:analysis:{pr_id}", 86400)
        except Exception as e:
            logger.warning(f"Failed to cache analysis: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "analysis"}


@app.post("/analyze", response_model=PRAnalysisResult)
async def analyze_endpoint(req: PRAnalysisRequest):
    """Direct HTTP endpoint for analysis (bypasses NATS)."""
    return await analyze_pr(req)


@app.get("/analysis/{pr_id}")
async def get_analysis(pr_id: str):
    """Get cached analysis for a PR."""
    if redis_client:
        data = await redis_client.hgetall(f"pr:analysis:{pr_id}")
        if data:
            return {"pr_id": pr_id, "source": "cache", **data}

    if db_pool:
        row = await db_pool.fetchrow(
            "SELECT complexity_score, risk_score, estimated_review_minutes FROM pull_requests WHERE id = $1",
            pr_id
        )
        if row:
            return {
                "pr_id": pr_id,
                "source": "db",
                "complexity_score": row["complexity_score"],
                "risk_score": row["risk_score"],
                "estimated_review_minutes": row["estimated_review_minutes"],
            }

    raise HTTPException(status_code=404, detail="Analysis not found")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)