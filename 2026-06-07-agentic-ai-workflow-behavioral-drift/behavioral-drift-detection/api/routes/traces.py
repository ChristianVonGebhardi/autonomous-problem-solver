"""Trace ingestion and retrieval endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import AgentTrace, Workflow
from api.schemas import TraceIngest, TraceResponse, DriftScoreResponse

router = APIRouter(prefix="/api/v1/traces", tags=["traces"])


@router.post("", response_model=dict, status_code=202)
async def ingest_trace(
    payload: TraceIngest,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a behavioral trace from the SDK.
    
    Returns immediately (202 Accepted) — drift detection happens async in the worker.
    """
    # Upsert workflow if not exists (allows SDK to emit before workflow is registered)
    result = await db.execute(
        select(Workflow).where(Workflow.id == payload.workflow_id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        workflow = Workflow(
            id=payload.workflow_id,
            name=f"Auto-registered: {payload.workflow_id[:8]}",
        )
        db.add(workflow)

    # Check for duplicate run_id
    result = await db.execute(
        select(AgentTrace).where(AgentTrace.run_id == payload.run_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {"status": "duplicate", "run_id": payload.run_id}

    trace = AgentTrace(
        run_id=payload.run_id,
        workflow_id=payload.workflow_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        duration_ms=payload.duration_ms,
        step_count=payload.step_count or len(payload.steps),
        tool_sequence=payload.tool_sequence or [s.tool_name for s in payload.steps],
        steps=[s.model_dump() for s in payload.steps],
        metadata=payload.metadata,
        error=payload.error,
        processed=False,
    )
    db.add(trace)
    await db.commit()

    return {"status": "accepted", "run_id": payload.run_id}


@router.get("/{run_id}", response_model=dict)
async def get_trace(run_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve a specific trace by run_id, including its drift score if processed."""
    from sqlalchemy.orm import selectinload
    from api.models import DriftScore

    result = await db.execute(
        select(AgentTrace).where(AgentTrace.run_id == run_id)
    )
    trace = result.scalar_one_or_none()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    drift_result = await db.execute(
        select(DriftScore).where(DriftScore.run_id == run_id)
    )
    drift = drift_result.scalar_one_or_none()

    return {
        "run_id": trace.run_id,
        "workflow_id": trace.workflow_id,
        "start_time": trace.start_time,
        "end_time": trace.end_time,
        "duration_ms": trace.duration_ms,
        "step_count": trace.step_count,
        "tool_sequence": trace.tool_sequence,
        "steps": trace.steps,
        "metadata": trace.metadata,
        "error": trace.error,
        "processed": trace.processed,
        "drift_score": {
            "composite_score": drift.composite_score,
            "structural_score": drift.structural_score,
            "semantic_score": drift.semantic_score,
            "distributional_score": drift.distributional_score,
            "severity": drift.severity,
            "alert_triggered": drift.alert_triggered,
            "explanation": drift.explanation,
            "structural_detail": drift.structural_detail,
            "semantic_detail": drift.semantic_detail,
            "distributional_detail": drift.distributional_detail,
        } if drift else None,
    }


@router.get("", response_model=list[dict])
async def list_traces(
    workflow_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """List recent traces, optionally filtered by workflow."""
    from api.models import DriftScore
    
    query = select(AgentTrace)
    if workflow_id:
        query = query.where(AgentTrace.workflow_id == workflow_id)
    query = query.order_by(desc(AgentTrace.start_time)).limit(limit).offset(offset)

    result = await db.execute(query)
    traces = result.scalars().all()

    output = []
    for trace in traces:
        drift_result = await db.execute(
            select(DriftScore).where(DriftScore.run_id == trace.run_id)
        )
        drift = drift_result.scalar_one_or_none()
        output.append({
            "run_id": trace.run_id,
            "workflow_id": trace.workflow_id,
            "start_time": trace.start_time,
            "step_count": trace.step_count,
            "tool_sequence": trace.tool_sequence,
            "processed": trace.processed,
            "composite_score": drift.composite_score if drift else None,
            "severity": drift.severity if drift else None,
            "alert_triggered": drift.alert_triggered if drift else False,
        })

    return output