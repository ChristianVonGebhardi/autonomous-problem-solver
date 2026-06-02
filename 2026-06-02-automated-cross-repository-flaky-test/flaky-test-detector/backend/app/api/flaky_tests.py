"""Flaky tests CRUD and listing endpoints."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog

from app.db.database import get_db

logger = structlog.get_logger()
router = APIRouter()


@router.get("/flaky-tests")
async def list_flaky_tests(
    repo: Optional[str] = Query(None, description="Filter by repository full name"),
    is_active: Optional[bool] = Query(None),
    cause: Optional[str] = Query(None, description="Filter by root cause"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List flaky tests with optional filters, sorted by flakiness score."""
    where_clauses = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if repo:
        where_clauses.append("r.full_name = :repo")
        params["repo"] = repo
    if is_active is not None:
        where_clauses.append("ft.is_active = :is_active")
        params["is_active"] = is_active
    if cause:
        where_clauses.append("rca.primary_cause = :cause")
        params["cause"] = cause

    where_sql = " AND ".join(where_clauses)

    query = text(f"""
        SELECT
            ft.id,
            r.full_name AS repo,
            ft.test_name,
            ft.test_file,
            ft.flakiness_score,
            ft.total_runs,
            ft.failed_runs,
            ft.pass_rate,
            ft.is_active,
            ft.first_detected_at,
            ft.last_seen_at,
            ft.last_analyzed_at,
            rca.primary_cause,
            rca.confidence AS cause_confidence,
            COUNT(DISTINCT fp.id) AS fix_count
        FROM flaky_tests ft
        JOIN repositories r ON ft.repo_id = r.id
        LEFT JOIN LATERAL (
            SELECT primary_cause, confidence
            FROM root_cause_analyses
            WHERE flaky_test_id = ft.id
            ORDER BY created_at DESC
            LIMIT 1
        ) rca ON TRUE
        LEFT JOIN fix_proposals fp ON fp.flaky_test_id = ft.id
        WHERE {where_sql}
        GROUP BY ft.id, r.full_name, rca.primary_cause, rca.confidence
        ORDER BY ft.flakiness_score DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(query, params)
    rows = result.mappings().all()

    count_query = text(f"""
        SELECT COUNT(DISTINCT ft.id)
        FROM flaky_tests ft
        JOIN repositories r ON ft.repo_id = r.id
        LEFT JOIN LATERAL (
            SELECT primary_cause FROM root_cause_analyses
            WHERE flaky_test_id = ft.id ORDER BY created_at DESC LIMIT 1
        ) rca ON TRUE
        WHERE {where_sql}
    """)
    count_result = await db.execute(count_query, {k: v for k, v in params.items() if k not in ("limit", "offset")})
    total = count_result.scalar()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }


@router.get("/flaky-tests/{flaky_test_id}")
async def get_flaky_test(
    flaky_test_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a single flaky test with full details."""
    result = await db.execute(
        text("""
            SELECT
                ft.*,
                r.full_name AS repo
            FROM flaky_tests ft
            JOIN repositories r ON ft.repo_id = r.id
            WHERE ft.id = :id
        """),
        {"id": flaky_test_id},
    )
    row = result.mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Flaky test not found")

    # Get recent run history
    runs_result = await db.execute(
        text("""
            SELECT status, created_at, duration_ms, error_message
            FROM test_runs
            WHERE repo_id = :repo_id AND test_name = :test_name
            ORDER BY created_at DESC
            LIMIT 30
        """),
        {"repo_id": row["repo_id"], "test_name": row["test_name"]},
    )
    runs = [dict(r) for r in runs_result.mappings().all()]

    return {**dict(row), "recent_runs": runs}


@router.patch("/flaky-tests/{flaky_test_id}")
async def update_flaky_test(
    flaky_test_id: int,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """Update a flaky test (e.g., mark as inactive/resolved)."""
    if is_active is None:
        raise HTTPException(status_code=400, detail="No update fields provided")

    result = await db.execute(
        text("SELECT id FROM flaky_tests WHERE id = :id"),
        {"id": flaky_test_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Flaky test not found")

    await db.execute(
        text("UPDATE flaky_tests SET is_active = :is_active WHERE id = :id"),
        {"is_active": is_active, "id": flaky_test_id},
    )
    await db.commit()
    return {"status": "updated", "id": flaky_test_id}


@router.get("/flaky-tests/{flaky_test_id}/run-history")
async def get_run_history(
    flaky_test_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get the run history for a flaky test."""
    # Get the test info first
    result = await db.execute(
        text("SELECT repo_id, test_name FROM flaky_tests WHERE id = :id"),
        {"id": flaky_test_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Flaky test not found")

    repo_id, test_name = row

    runs_result = await db.execute(
        text("""
            SELECT id, status, duration_ms, branch, commit_sha,
                   error_message, created_at
            FROM test_runs
            WHERE repo_id = :repo_id AND test_name = :test_name
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"repo_id": repo_id, "test_name": test_name, "limit": limit},
    )
    runs = [dict(r) for r in runs_result.mappings().all()]
    return {"test_name": test_name, "runs": runs}


@router.get("/repositories")
async def list_repositories(
    db: AsyncSession = Depends(get_db),
):
    """List all monitored repositories."""
    result = await db.execute(
        text("""
            SELECT 
                r.id, r.full_name, r.ci_system, r.default_branch, r.created_at,
                COUNT(DISTINCT ft.id) AS flaky_test_count,
                COUNT(DISTINCT tr.id) AS total_runs
            FROM repositories r
            LEFT JOIN flaky_tests ft ON ft.repo_id = r.id AND ft.is_active = TRUE
            LEFT JOIN test_runs tr ON tr.repo_id = r.id
            GROUP BY r.id
            ORDER BY flaky_test_count DESC
        """)
    )
    rows = result.mappings().all()
    return {"items": [dict(r) for r in rows]}