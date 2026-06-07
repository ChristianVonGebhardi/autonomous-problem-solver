"""Baseline (golden run) management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import AgentTrace, BaselineRun, Workflow
from api.schemas import BaselineCreate, BaselineResponse

router = APIRouter(prefix="/api/v1/baselines", tags=["baselines"])


@router.post("/{workflow_id}", response_model=BaselineResponse, status_code=201)
async def approve_baseline(
    workflow_id: str,
    payload: BaselineCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a trace as a golden run baseline for a workflow.
    
    The worker will generate embeddings and register this as the behavioral baseline
    for structural, semantic, and distributional comparison.
    """
    # Validate workflow exists
    wf_result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Validate trace exists
    trace_result = await db.execute(
        select(AgentTrace).where(AgentTrace.run_id == payload.run_id)
    )
    trace = trace_result.scalar_one_or_none()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found — ingest it first")

    if trace.workflow_id != workflow_id:
        raise HTTPException(
            status_code=400,
            detail="Trace belongs to a different workflow"
        )

    # Check for existing baseline for this run_id
    existing = await db.execute(
        select(BaselineRun).where(
            BaselineRun.workflow_id == workflow_id,
            BaselineRun.run_id == payload.run_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Baseline already exists for this run")

    baseline = BaselineRun(
        workflow_id=workflow_id,
        run_id=payload.run_id,
        tool_sequence=trace.tool_sequence or [],
        approved_by=payload.approved_by,
        notes=payload.notes,
        # Embeddings will be populated by the baseline processor worker
        step_embeddings=None,
        run_embedding=None,
    )
    db.add(baseline)
    await db.commit()
    await db.refresh(baseline)
    return baseline


@router.get("/{workflow_id}", response_model=list[BaselineResponse])
async def list_baselines(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """List all golden run baselines for a workflow."""
    result = await db.execute(
        select(BaselineRun).where(BaselineRun.workflow_id == workflow_id)
    )
    return result.scalars().all()


@router.delete("/{workflow_id}/{baseline_id}", status_code=204)
async def delete_baseline(
    workflow_id: str,
    baseline_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BaselineRun).where(
            BaselineRun.id == baseline_id,
            BaselineRun.workflow_id == workflow_id,
        )
    )
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    await db.delete(baseline)
    await db.commit()