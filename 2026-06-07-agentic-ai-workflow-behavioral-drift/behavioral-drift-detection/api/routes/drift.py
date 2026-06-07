"""Drift score query and time-series endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import DriftScore
from api.schemas import DriftScoreResponse, DriftTimeSeriesPoint

router = APIRouter(prefix="/api/v1/drift", tags=["drift"])


@router.get("/timeseries/{workflow_id}", response_model=list[DriftTimeSeriesPoint])
async def get_drift_timeseries(
    workflow_id: str,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    """
    Return drift score time series for a workflow.
    
    Suitable for feeding directly into Recharts or Prometheus exporters.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(DriftScore)
        .where(DriftScore.workflow_id == workflow_id)
        .where(DriftScore.ingested_at >= cutoff)
        .order_by(DriftScore.ingested_at)
    )
    scores = result.scalars().all()

    return [
        DriftTimeSeriesPoint(
            timestamp=s.ingested_at,
            run_id=s.run_id,
            composite_score=s.composite_score or 0.0,
            structural_score=s.structural_score,
            semantic_score=s.semantic_score,
            distributional_score=s.distributional_score,
            severity=s.severity,
            alert_triggered=s.alert_triggered,
        )
        for s in scores
    ]


@router.get("/alerts/{workflow_id}", response_model=list[DriftScoreResponse])
async def get_alerts(
    workflow_id: str,
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return recent alert-triggering drift events for a workflow."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(DriftScore)
        .where(DriftScore.workflow_id == workflow_id)
        .where(DriftScore.alert_triggered == True)
        .where(DriftScore.ingested_at >= cutoff)
        .order_by(desc(DriftScore.ingested_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/score/{run_id}", response_model=DriftScoreResponse)
async def get_drift_score(run_id: str, db: AsyncSession = Depends(get_db)):
    """Get the drift score for a specific run."""
    from fastapi import HTTPException
    result = await db.execute(
        select(DriftScore).where(DriftScore.run_id == run_id)
    )
    score = result.scalar_one_or_none()
    if not score:
        raise HTTPException(status_code=404, detail="Drift score not found (run may not be processed yet)")
    return score


@router.get("/latest/{workflow_id}", response_model=Optional[DriftScoreResponse])
async def get_latest_score(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Get the most recent drift score for a workflow."""
    result = await db.execute(
        select(DriftScore)
        .where(DriftScore.workflow_id == workflow_id)
        .order_by(desc(DriftScore.ingested_at))
        .limit(1)
    )
    return result.scalar_one_or_none()