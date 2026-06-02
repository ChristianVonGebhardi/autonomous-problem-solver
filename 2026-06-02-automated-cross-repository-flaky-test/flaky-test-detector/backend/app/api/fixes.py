"""Fix proposal endpoints."""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog
import redis.asyncio as aioredis

from app.db.database import get_db
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()


async def get_redis():
    client = aioredis.from_url(settings.redis_url)
    try:
        yield client
    finally:
        await client.aclose()


@router.get("/fixes")
async def list_fixes(
    status: Optional[str] = Query(None, description="pending|synthesizing|proposed|accepted|rejected"),
    flaky_test_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List fix proposals."""
    where_clauses = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if status:
        where_clauses.append("fp.status = :status")
        params["status"] = status
    if flaky_test_id:
        where_clauses.append("fp.flaky_test_id = :flaky_test_id")
        params["flaky_test_id"] = flaky_test_id

    where_sql = " AND ".join(where_clauses)

    result = await db.execute(
        text(f"""
            SELECT
                fp.id, fp.flaky_test_id, fp.status, fp.root_cause,
                fp.explanation, fp.affected_files, fp.confidence,
                fp.pr_url, fp.pr_number, fp.feedback_accepted,
                fp.llm_model, fp.created_at, fp.updated_at,
                ft.test_name, ft.test_file, r.full_name AS repo
            FROM fix_proposals fp
            JOIN flaky_tests ft ON fp.flaky_test_id = ft.id
            JOIN repositories r ON ft.repo_id = r.id
            WHERE {where_sql}
            ORDER BY fp.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    rows = result.mappings().all()

    count_result = await db.execute(
        text(f"""
            SELECT COUNT(*) FROM fix_proposals fp
            JOIN flaky_tests ft ON fp.flaky_test_id = ft.id
            JOIN repositories r ON ft.repo_id = r.id
            WHERE {where_sql}
        """),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )
    total = count_result.scalar()

    return {"total": total, "limit": limit, "offset": offset, "items": [dict(r) for r in rows]}


@router.get("/fixes/{fix_id}")
async def get_fix(
    fix_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific fix proposal including the patch diff."""
    result = await db.execute(
        text("""
            SELECT
                fp.*, ft.test_name, ft.test_file, r.full_name AS repo
            FROM fix_proposals fp
            JOIN flaky_tests ft ON fp.flaky_test_id = ft.id
            JOIN repositories r ON ft.repo_id = r.id
            WHERE fp.id = :id
        """),
        {"id": fix_id},
    )
    row = result.mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Fix proposal not found")
    return dict(row)


@router.post("/fixes/{fix_id}/feedback")
async def submit_feedback(
    fix_id: int,
    accepted: bool,
    note: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis),
):
    """Submit developer feedback (accept/reject) on a fix proposal."""
    result = await db.execute(
        text("SELECT id, flaky_test_id, root_cause FROM fix_proposals WHERE id = :id"),
        {"id": fix_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Fix proposal not found")

    new_status = "accepted" if accepted else "rejected"

    await db.execute(
        text("""
            UPDATE fix_proposals SET
                feedback_accepted = :accepted,
                feedback_note = :note,
                status = :status,
                updated_at = NOW()
            WHERE id = :id
        """),
        {"accepted": accepted, "note": note, "status": new_status, "id": fix_id},
    )
    await db.commit()

    # Publish feedback event for retraining pipeline
    await redis_client.publish(
        "flaky_events",
        json.dumps({
            "type": "fix_feedback",
            "fix_id": fix_id,
            "accepted": accepted,
            "note": note,
            "flaky_test_id": row[1],
            "root_cause": row[2],
        }),
    )

    # Store in retraining queue
    await redis_client.lpush(
        "feedback_queue",
        json.dumps({
            "fix_id": fix_id,
            "accepted": accepted,
            "note": note,
        }),
    )

    logger.info("feedback_submitted", fix_id=fix_id, accepted=accepted)
    return {"status": "feedback_recorded", "fix_status": new_status}


@router.post("/fixes/trigger/{flaky_test_id}")
async def trigger_fix_synthesis(
    flaky_test_id: int,
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis),
):
    """Manually trigger fix synthesis for a flaky test."""
    result = await db.execute(
        text("""
            SELECT ft.id, ft.test_name, ft.test_file,
                   r.full_name AS repo,
                   rca.primary_cause, rca.confidence
            FROM flaky_tests ft
            JOIN repositories r ON ft.repo_id = r.id
            LEFT JOIN LATERAL (
                SELECT primary_cause, confidence
                FROM root_cause_analyses
                WHERE flaky_test_id = ft.id
                ORDER BY created_at DESC LIMIT 1
            ) rca ON TRUE
            WHERE ft.id = :id
        """),
        {"id": flaky_test_id},
    )
    row = result.mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Flaky test not found")

    job = {
        "flaky_test_id": flaky_test_id,
        "test_name": row["test_name"],
        "test_file": row["test_file"],
        "root_cause": row["primary_cause"] or "unknown",
        "repo": row["repo"],
        "log_output": "",
        "error_message": "",
    }
    await redis_client.lpush("fix_synthesis_queue", json.dumps(job))

    return {"status": "queued", "flaky_test_id": flaky_test_id}