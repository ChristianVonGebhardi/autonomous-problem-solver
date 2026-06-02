"""CI event ingestion endpoints."""
import json
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog
import redis.asyncio as aioredis

from app.db.database import get_db
from app.schemas.events import TestExecutionEvent, GitHubActionsWebhook
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()


async def get_redis():
    client = aioredis.from_url(settings.redis_url)
    try:
        yield client
    finally:
        await client.aclose()


async def ingest_event(event: TestExecutionEvent, db: AsyncSession, redis_client):
    """Core ingestion logic: save to DB and queue for analysis."""
    # Get or create repository
    result = await db.execute(
        text("SELECT id FROM repositories WHERE full_name = :name"),
        {"name": event.repo},
    )
    repo_row = result.fetchone()
    
    if repo_row:
        repo_id = repo_row[0]
    else:
        result = await db.execute(
            text(
                "INSERT INTO repositories (full_name, ci_system) VALUES (:name, :ci) RETURNING id"
            ),
            {"name": event.repo, "ci": event.ci_system.value},
        )
        repo_id = result.fetchone()[0]
        await db.commit()
    
    # Save test run
    result = await db.execute(
        text("""
            INSERT INTO test_runs (
                repo_id, test_name, test_file, test_class, branch, commit_sha,
                pipeline_id, status, duration_ms, log_output, error_message,
                stack_trace, ci_system, environment_vars
            ) VALUES (
                :repo_id, :test_name, :test_file, :test_class, :branch, :commit_sha,
                :pipeline_id, :status, :duration_ms, :log_output, :error_message,
                :stack_trace, :ci_system, :environment_vars
            ) RETURNING id
        """),
        {
            "repo_id": repo_id,
            "test_name": event.test_name,
            "test_file": event.test_file,
            "test_class": event.test_class,
            "branch": event.branch,
            "commit_sha": event.commit_sha,
            "pipeline_id": event.pipeline_id,
            "status": event.status.value,
            "duration_ms": event.duration_ms,
            "log_output": event.log_output,
            "error_message": event.error_message,
            "stack_trace": event.stack_trace,
            "ci_system": event.ci_system.value,
            "environment_vars": json.dumps(event.environment_vars) if event.environment_vars else None,
        },
    )
    run_id = result.fetchone()[0]
    await db.commit()
    
    # Queue for flakiness analysis
    event_payload = json.dumps({
        "run_id": run_id,
        "repo": event.repo,
        "test_name": event.test_name,
        "test_file": event.test_file,
        "status": event.status.value,
        "ci_system": event.ci_system.value,
    })
    await redis_client.lpush("test_events_queue", event_payload)
    
    # Publish real-time event
    await redis_client.publish("flaky_events", json.dumps({
        "type": "test_run_ingested",
        "repo": event.repo,
        "test_name": event.test_name,
        "status": event.status.value,
        "run_id": run_id,
    }))
    
    logger.info(
        "event_ingested",
        run_id=run_id,
        repo=event.repo,
        test=event.test_name,
        status=event.status.value,
    )
    
    return {"run_id": run_id, "status": "queued"}


@router.post("/events/ingest")
async def ingest_test_event(
    event: TestExecutionEvent,
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis),
):
    """Ingest a single test execution event from any CI system."""
    return await ingest_event(event, db, redis_client)


@router.post("/events/ingest/batch")
async def ingest_batch(
    events: list[TestExecutionEvent],
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis),
):
    """Ingest multiple test events in a single request."""
    if len(events) > 1000:
        raise HTTPException(status_code=400, detail="Max 1000 events per batch")
    
    results = []
    for event in events:
        result = await ingest_event(event, db, redis_client)
        results.append(result)
    
    return {"ingested": len(results), "results": results}


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis),
):
    """GitHub Actions webhook receiver."""
    # Verify webhook signature in production
    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event", "")
    
    if event_type not in ("check_run", "workflow_run"):
        return {"status": "ignored", "event_type": event_type}
    
    try:
        webhook = GitHubActionsWebhook(**payload)
        events = webhook.to_canonical()
        for event in events:
            await ingest_event(event, db, redis_client)
        return {"status": "processed", "events": len(events)}
    except Exception as e:
        logger.error("webhook_processing_failed", error=str(e))
        raise HTTPException(status_code=422, detail=str(e))