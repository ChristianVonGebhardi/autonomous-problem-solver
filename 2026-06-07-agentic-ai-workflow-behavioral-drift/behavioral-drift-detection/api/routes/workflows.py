"""Workflow registration and management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Workflow, AgentTrace, BaselineRun, DriftScore
from api.schemas import WorkflowCreate, WorkflowUpdate, WorkflowResponse, WorkflowDriftSummary

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    payload: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    workflow = Workflow(**payload.model_dump())
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).order_by(desc(Workflow.created_at)))
    return result.scalars().all()


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(workflow, key, value)
    
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("/{workflow_id}/summary", response_model=WorkflowDriftSummary)
async def get_workflow_summary(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Get a summary of drift health for a workflow."""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)

    # Recent drift scores
    scores_result = await db.execute(
        select(DriftScore)
        .where(DriftScore.workflow_id == workflow_id)
        .where(DriftScore.ingested_at >= cutoff)
        .order_by(desc(DriftScore.ingested_at))
        .limit(20)
    )
    recent_scores = scores_result.scalars().all()

    # Baseline count
    baseline_result = await db.execute(
        select(func.count()).where(BaselineRun.workflow_id == workflow_id)
    )
    baseline_count = baseline_result.scalar() or 0

    # Trace count (24h)
    trace_result = await db.execute(
        select(func.count())
        .select_from(AgentTrace)
        .where(AgentTrace.workflow_id == workflow_id)
    )
    # Use all traces for now
    trace_count = trace_result.scalar() or 0

    alert_count = sum(1 for s in recent_scores if s.alert_triggered)
    
    # Determine trend
    recent_composite = None
    trend = "stable"
    if recent_scores:
        recent_composite = recent_scores[0].composite_score
        if len(recent_scores) >= 4:
            first_half = [s.composite_score for s in recent_scores[len(recent_scores)//2:] if s.composite_score]
            second_half = [s.composite_score for s in recent_scores[:len(recent_scores)//2] if s.composite_score]
            if first_half and second_half:
                if sum(second_half)/len(second_half) > sum(first_half)/len(first_half) + 0.05:
                    trend = "increasing"
                elif sum(second_half)/len(second_half) < sum(first_half)/len(first_half) - 0.05:
                    trend = "decreasing"

    last_alert = next((s.ingested_at for s in recent_scores if s.alert_triggered), None)

    return WorkflowDriftSummary(
        workflow_id=workflow_id,
        workflow_name=workflow.name,
        recent_composite_score=recent_composite,
        trend=trend,
        alert_count_24h=alert_count,
        baseline_count=baseline_count,
        trace_count_24h=trace_count,
        last_alert_at=last_alert,
    )