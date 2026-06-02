"""Dashboard statistics and trends endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog

from app.db.database import get_db

logger = structlog.get_logger()
router = APIRouter()


@router.get("/dashboard/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get high-level dashboard statistics."""

    # Totals
    totals = await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM repositories) AS total_repos,
            (SELECT COUNT(*) FROM test_runs) AS total_test_runs,
            (SELECT COUNT(*) FROM flaky_tests) AS total_flaky_tests,
            (SELECT COUNT(*) FROM flaky_tests WHERE is_active = TRUE) AS active_flaky_tests,
            (SELECT COUNT(*) FROM fix_proposals) AS fixes_proposed,
            (SELECT COUNT(*) FROM fix_proposals WHERE feedback_accepted = TRUE) AS fixes_accepted,
            (SELECT COUNT(*) FROM fix_proposals WHERE feedback_accepted = FALSE) AS fixes_rejected
    """))
    row = totals.mappings().fetchone()
    stats = dict(row)

    # Acceptance rate
    if stats["fixes_proposed"] > 0:
        stats["acceptance_rate"] = round(
            stats["fixes_accepted"] / max(stats["fixes_accepted"] + stats["fixes_rejected"], 1), 3
        )
    else:
        stats["acceptance_rate"] = 0.0

    # Cause breakdown
    cause_result = await db.execute(text("""
        SELECT primary_cause, COUNT(*) AS cnt
        FROM root_cause_analyses rca
        JOIN (
            SELECT flaky_test_id, MAX(id) AS max_id
            FROM root_cause_analyses
            GROUP BY flaky_test_id
        ) latest ON rca.id = latest.max_id
        GROUP BY primary_cause
        ORDER BY cnt DESC
    """))
    stats["cause_breakdown"] = {
        row["primary_cause"]: row["cnt"]
        for row in cause_result.mappings().all()
    }

    # Top flaky tests
    top_result = await db.execute(text("""
        SELECT
            ft.id, ft.test_name, ft.flakiness_score, ft.total_runs,
            ft.failed_runs, ft.pass_rate, r.full_name AS repo,
            rca.primary_cause
        FROM flaky_tests ft
        JOIN repositories r ON ft.repo_id = r.id
        LEFT JOIN LATERAL (
            SELECT primary_cause FROM root_cause_analyses
            WHERE flaky_test_id = ft.id ORDER BY created_at DESC LIMIT 1
        ) rca ON TRUE
        WHERE ft.is_active = TRUE
        ORDER BY ft.flakiness_score DESC
        LIMIT 10
    """))
    stats["top_flaky_tests"] = [dict(r) for r in top_result.mappings().all()]

    return stats


@router.get("/dashboard/trends")
async def get_trends(
    repo: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get flakiness trends over time (daily buckets)."""
    params: dict = {"days": days}
    repo_filter = ""
    if repo:
        repo_filter = "AND r.full_name = :repo"
        params["repo"] = repo

    result = await db.execute(
        text(f"""
            SELECT
                DATE_TRUNC('day', tr.created_at) AS day,
                COUNT(*) AS total_runs,
                COUNT(*) FILTER (WHERE tr.status != 'passed') AS failed_runs,
                COUNT(DISTINCT tr.test_name) AS unique_tests
            FROM test_runs tr
            JOIN repositories r ON tr.repo_id = r.id
            WHERE tr.created_at >= NOW() - INTERVAL '1 day' * :days
            {repo_filter}
            GROUP BY 1
            ORDER BY 1
        """),
        params,
    )
    rows = result.mappings().all()
    return {"days": days, "data": [dict(r) for r in rows]}


@router.get("/dashboard/cause-trends")
async def get_cause_trends(
    repo: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get root cause distribution trends over time."""
    params: dict = {"days": days}
    repo_filter = ""
    if repo:
        repo_filter = "AND r.full_name = :repo"
        params["repo"] = repo

    result = await db.execute(
        text(f"""
            SELECT
                DATE_TRUNC('day', rca.created_at) AS day,
                rca.primary_cause,
                COUNT(*) AS count
            FROM root_cause_analyses rca
            JOIN flaky_tests ft ON rca.flaky_test_id = ft.id
            JOIN repositories r ON ft.repo_id = r.id
            WHERE rca.created_at >= NOW() - INTERVAL '1 day' * :days
            {repo_filter}
            GROUP BY 1, 2
            ORDER BY 1, 2
        """),
        params,
    )
    rows = result.mappings().all()
    return {"days": days, "data": [dict(r) for r in rows]}


@router.get("/dashboard/fix-stats")
async def get_fix_stats(db: AsyncSession = Depends(get_db)):
    """Get fix proposal statistics by status and root cause."""
    by_status = await db.execute(text("""
        SELECT status, COUNT(*) AS count
        FROM fix_proposals
        GROUP BY status
        ORDER BY count DESC
    """))

    by_cause = await db.execute(text("""
        SELECT root_cause, 
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE feedback_accepted = TRUE) AS accepted,
               COUNT(*) FILTER (WHERE feedback_accepted = FALSE) AS rejected,
               AVG(confidence) AS avg_confidence
        FROM fix_proposals
        WHERE root_cause IS NOT NULL
        GROUP BY root_cause
        ORDER BY total DESC
    """))

    return {
        "by_status": [dict(r) for r in by_status.mappings().all()],
        "by_cause": [dict(r) for r in by_cause.mappings().all()],
    }