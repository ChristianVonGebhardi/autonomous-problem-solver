"""Root cause analysis endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog

from app.db.database import get_db

logger = structlog.get_logger()
router = APIRouter()


@router.get("/analyses")
async def list_analyses(
    flaky_test_id: Optional[int] = Query(None),
    cause: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List root cause analyses."""
    where_clauses = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if flaky_test_id:
        where_clauses.append("rca.flaky_test_id = :flaky_test_id")
        params["flaky_test_id"] = flaky_test_id
    if cause:
        where_clauses.append("rca.primary_cause = :cause")
        params["cause"] = cause

    where_sql = " AND ".join(where_clauses)

    result = await db.execute(
        text(f"""
            SELECT
                rca.id, rca.flaky_test_id, rca.primary_cause, rca.confidence,
                rca.secondary_causes, rca.evidence, rca.classifier_version,
                rca.created_at, ft.test_name, r.full_name AS repo
            FROM root_cause_analyses rca
            JOIN flaky_tests ft ON rca.flaky_test_id = ft.id
            JOIN repositories r ON ft.repo_id = r.id
            WHERE {where_sql}
            ORDER BY rca.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    rows = result.mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.get("/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific root cause analysis."""
    result = await db.execute(
        text("""
            SELECT
                rca.*, ft.test_name, ft.test_file, r.full_name AS repo
            FROM root_cause_analyses rca
            JOIN flaky_tests ft ON rca.flaky_test_id = ft.id
            JOIN repositories r ON ft.repo_id = r.id
            WHERE rca.id = :id
        """),
        {"id": analysis_id},
    )
    row = result.mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return dict(row)


@router.post("/analyses/classify")
async def classify_on_demand(
    log_output: str = "",
    error_message: str = "",
    stack_trace: str = "",
):
    """
    On-demand classification endpoint — classify failure text without storing.
    Useful for testing the classifier.
    """
    from app.services.root_cause_classifier import classify_failure
    result = classify_failure(
        log_output=log_output,
        error_message=error_message,
        stack_trace=stack_trace,
        use_ml=False,
    )
    return {
        "primary_cause": result.primary_cause,
        "confidence": result.confidence,
        "secondary_causes": result.secondary_causes,
        "evidence": result.evidence,
        "classifier_version": result.classifier_version,
    }