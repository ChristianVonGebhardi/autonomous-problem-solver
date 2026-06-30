"""
FastAPI Control Plane

REST API for:
- Workflow registration and management
- Trace ingestion
- Baseline management
- Drift score queries
- Alert management
"""

import os
import sys
import logging
from datetime import datetime, timezone
from typing import List, Optional
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db, engine, Base
from backend.db import models
from backend.db.models import Workflow, TraceRun, SpanRecord, DriftScore, Alert
from backend.models.schemas import (
    WorkflowCreate, WorkflowResponse,
    TraceIngestion, TraceResponse,
    DriftScoreResponse, DriftTimelineResponse,
    AlertResponse,
    BaselinePromoteRequest, BaselineResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(
    title="Behavioral Drift Detection API",
    description="Detect when agentic AI workflows silently deviate from intended behavior",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized.")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── Workflows ─────────────────────────────────────────────────────────────────

@app.post("/api/workflows", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    payload: WorkflowCreate, db: AsyncSession = Depends(get_db)
):
    # Check for duplicate
    existing = await db.execute(
        select(Workflow).where(Workflow.workflow_id == payload.workflow_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Workflow already exists")

    workflow = Workflow(
        workflow_id=payload.workflow_id,
        name=payload.name,
        description=payload.description,
        expected_steps=payload.expected_steps,
        expected_tools=payload.expected_tools,
        metadata_=payload.metadata,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)
    return workflow


@app.get("/api/workflows", response_model=List[WorkflowResponse])
async def list_workflows(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).order_by(Workflow.created_at.desc()))
    return result.scalars().all()


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Workflow).where(Workflow.workflow_id == workflow_id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


# ── Trace Ingestion ───────────────────────────────────────────────────────────

@app.post("/api/traces", status_code=201)
async def ingest_trace(payload: TraceIngestion, db: AsyncSession = Depends(get_db)):
    """Ingest a completed trace run from the SDK."""

    # Ensure workflow exists (auto-create if not registered)
    wf_result = await db.execute(
        select(Workflow).where(Workflow.workflow_id == payload.workflow_id)
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        workflow = Workflow(
            workflow_id=payload.workflow_id,
            name=payload.workflow_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(workflow)
        await db.flush()

    # Check for duplicate run
    existing = await db.execute(
        select(TraceRun).where(TraceRun.run_id == payload.run_id)
    )
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "run_id": payload.run_id}

    # Compute run-level embedding from span embeddings
    run_embedding = _compute_run_embedding(payload)

    start_dt = datetime.utcfromtimestamp(payload.start_time)
    end_dt = datetime.utcfromtimestamp(payload.end_time) if payload.end_time else None

    run = TraceRun(
        run_id=payload.run_id,
        workflow_id=payload.workflow_id,
        start_time=start_dt,
        end_time=end_dt,
        span_count=payload.span_count or len(payload.spans),
        is_baseline=False,
        avg_confidence=payload.avg_confidence,
        tool_sequence=payload.tool_sequence,
        step_sequence=payload.step_sequence,
        run_embedding=run_embedding,
        metadata_=payload.metadata,
        created_at=datetime.utcnow(),
    )
    db.add(run)
    await db.flush()

    # Persist individual spans
    for span_data in payload.spans:
        span = SpanRecord(
            span_id=span_data.span_id,
            run_id=payload.run_id,
            workflow_id=payload.workflow_id,
            step_name=span_data.step_name,
            step_index=span_data.step_index,
            tool_name=span_data.tool_name,
            tool_input=span_data.tool_input,
            reasoning=span_data.reasoning,
            output=span_data.output,
            confidence=span_data.confidence,
            retrieved_chunk_hashes=span_data.retrieved_chunk_hashes,
            token_count=span_data.token_count,
            latency_ms=span_data.latency_ms,
            start_time=datetime.utcfromtimestamp(span_data.start_time) if span_data.start_time else None,
            reasoning_embedding=span_data.reasoning_embedding,
            attributes=span_data.attributes,
            created_at=datetime.utcnow(),
        )
        db.add(span)

    logger.info(f"Ingested trace {payload.run_id} for workflow {payload.workflow_id}")
    return {"status": "accepted", "run_id": payload.run_id}


def _compute_run_embedding(payload: TraceIngestion) -> Optional[list]:
    """Aggregate span embeddings into a single run embedding."""
    embeddings = [
        s.reasoning_embedding
        for s in payload.spans
        if s.reasoning_embedding
    ]
    if not embeddings:
        return None

    arr = np.array(embeddings, dtype=np.float32)
    mean_emb = np.mean(arr, axis=0)
    norm = np.linalg.norm(mean_emb)
    if norm > 0:
        mean_emb = mean_emb / norm
    return mean_emb.tolist()


# ── Baseline Management ───────────────────────────────────────────────────────

@app.post("/api/baselines/{workflow_id}", response_model=BaselineResponse)
async def promote_baseline(
    workflow_id: str,
    payload: BaselinePromoteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Promote a trace run to golden baseline status."""
    run_result = await db.execute(
        select(TraceRun).where(
            and_(
                TraceRun.run_id == payload.run_id,
                TraceRun.workflow_id == workflow_id,
            )
        )
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Trace run not found")

    run.is_baseline = True

    # Update workflow baseline count
    wf_result = await db.execute(
        select(Workflow).where(Workflow.workflow_id == workflow_id)
    )
    workflow = wf_result.scalar_one_or_none()
    if workflow:
        # Count baselines
        count_result = await db.execute(
            select(func.count(TraceRun.id)).where(
                and_(
                    TraceRun.workflow_id == workflow_id,
                    TraceRun.is_baseline == True,
                )
            )
        )
        baseline_count = count_result.scalar() or 0
        workflow.baseline_count = baseline_count
        workflow.updated_at = datetime.utcnow()

    logger.info(f"Promoted run {payload.run_id} to baseline for {workflow_id}")

    return BaselineResponse(
        success=True,
        message="Run promoted to baseline",
        workflow_id=workflow_id,
        run_id=payload.run_id,
        baseline_count=workflow.baseline_count if workflow else 1,
    )


@app.get("/api/baselines/{workflow_id}")
async def list_baselines(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """List all baseline runs for a workflow."""
    result = await db.execute(
        select(TraceRun).where(
            and_(
                TraceRun.workflow_id == workflow_id,
                TraceRun.is_baseline == True,
            )
        ).order_by(TraceRun.start_time.desc())
    )
    baselines = result.scalars().all()
    return [
        {
            "run_id": b.run_id,
            "start_time": b.start_time.isoformat(),
            "span_count": b.span_count,
            "avg_confidence": b.avg_confidence,
            "tool_sequence": b.tool_sequence,
        }
        for b in baselines
    ]


# ── Drift Scores ──────────────────────────────────────────────────────────────

@app.get("/api/drift/{workflow_id}", response_model=DriftTimelineResponse)
async def get_drift_timeline(
    workflow_id: str,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get drift score timeline for a workflow."""
    result = await db.execute(
        select(DriftScore)
        .where(DriftScore.workflow_id == workflow_id)
        .order_by(DriftScore.timestamp.desc())
        .limit(limit)
    )
    scores = result.scalars().all()
    scores_reversed = list(reversed(scores))

    # Baseline count
    bc_result = await db.execute(
        select(func.count(TraceRun.id)).where(
            and_(
                TraceRun.workflow_id == workflow_id,
                TraceRun.is_baseline == True,
            )
        )
    )
    baseline_count = bc_result.scalar() or 0

    latest = scores[0] if scores else None

    return DriftTimelineResponse(
        workflow_id=workflow_id,
        scores=[
            DriftScoreResponse(
                id=s.id,
                workflow_id=s.workflow_id,
                run_id=s.run_id,
                timestamp=s.timestamp,
                structural_score=s.structural_score,
                semantic_score=s.semantic_score,
                distributional_score=s.distributional_score,
                composite_score=s.composite_score,
                alert_level=s.alert_level,
                details=s.details,
            )
            for s in scores_reversed
        ],
        baseline_count=baseline_count,
        latest_composite=latest.composite_score if latest else None,
        alert_level=latest.alert_level if latest else None,
    )


@app.get("/api/drift/{workflow_id}/latest")
async def get_latest_drift(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Get the most recent drift score for a workflow."""
    result = await db.execute(
        select(DriftScore)
        .where(DriftScore.workflow_id == workflow_id)
        .order_by(DriftScore.timestamp.desc())
        .limit(1)
    )
    score = result.scalar_one_or_none()
    if not score:
        return {"workflow_id": workflow_id, "status": "no_data"}
    return {
        "workflow_id": workflow_id,
        "run_id": score.run_id,
        "composite_score": score.composite_score,
        "alert_level": score.alert_level,
        "structural_score": score.structural_score,
        "semantic_score": score.semantic_score,
        "distributional_score": score.distributional_score,
        "timestamp": score.timestamp.isoformat(),
    }


# ── Alerts ────────────────────────────────────────────────────────────────────

@app.get("/api/alerts", response_model=List[AlertResponse])
async def list_alerts(
    workflow_id: Optional[str] = None,
    unacknowledged_only: bool = False,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List alerts, optionally filtered by workflow."""
    query = select(Alert).order_by(desc(Alert.created_at)).limit(limit)
    if workflow_id:
        query = query.where(Alert.workflow_id == workflow_id)
    if unacknowledged_only:
        query = query.where(Alert.acknowledged == False)

    result = await db.execute(query)
    return result.scalars().all()


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Mark an alert as acknowledged."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    return {"status": "acknowledged", "alert_id": alert_id}


# ── Traces ────────────────────────────────────────────────────────────────────

@app.get("/api/traces/{workflow_id}")
async def get_traces(
    workflow_id: str,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get recent trace runs for a workflow."""
    result = await db.execute(
        select(TraceRun)
        .where(TraceRun.workflow_id == workflow_id)
        .order_by(TraceRun.created_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()
    return [
        {
            "run_id": r.run_id,
            "is_baseline": r.is_baseline,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "span_count": r.span_count,
            "avg_confidence": r.avg_confidence,
            "tool_sequence": r.tool_sequence,
            "step_sequence": r.step_sequence,
        }
        for r in runs
    ]


# ── Summary stats ─────────────────────────────────────────────────────────────

@app.get("/api/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    """Dashboard summary statistics."""
    wf_count = (await db.execute(select(func.count(Workflow.id)))).scalar() or 0
    trace_count = (await db.execute(select(func.count(TraceRun.id)))).scalar() or 0
    alert_count = (
        await db.execute(
            select(func.count(Alert.id)).where(Alert.acknowledged == False)
        )
    ).scalar() or 0
    baseline_count = (
        await db.execute(
            select(func.count(TraceRun.id)).where(TraceRun.is_baseline == True)
        )
    ).scalar() or 0

    return {
        "workflow_count": wf_count,
        "trace_count": trace_count,
        "active_alerts": alert_count,
        "baseline_count": baseline_count,
    }