"""
Dashboard API — serves metrics, alerts, and management endpoints.
"""
import uuid
import numpy as np
import structlog
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from pydantic import BaseModel

from app.database import get_db
from app.models import (
    PromptTemplate, GoldenReference, InferenceLog,
    QualityScore, DriftAlert, MetricAggregate
)
from app.config import settings

logger = structlog.get_logger()

app = FastAPI(title="LLM Quality Monitor - API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class GoldenReferenceCreate(BaseModel):
    template_id: str
    input_messages: List[Dict[str, Any]]
    expected_output: str
    metadata: Dict[str, Any] = {}


class GoldenReferenceResponse(BaseModel):
    id: str
    template_id: str
    expected_output: str
    created_at: datetime

    class Config:
        from_attributes = True


class MetricPoint(BaseModel):
    timestamp: datetime
    value: float
    sample_count: Optional[int] = None


class MetricSeries(BaseModel):
    metric_name: str
    template_name: str
    points: List[MetricPoint]
    baseline_mean: Optional[float] = None
    current_mean: Optional[float] = None


class AlertResponse(BaseModel):
    id: str
    template_name: Optional[str]
    metric_name: str
    severity: str
    detector_type: str
    baseline_mean: Optional[float]
    current_mean: Optional[float]
    p_value: Optional[float]
    cusum_stat: Optional[float]
    evidence: Dict[str, Any]
    acknowledged: bool
    created_at: datetime

    class Config:
        from_attributes = True


class InferenceLogResponse(BaseModel):
    id: str
    template_name: Optional[str]
    model: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    latency_ms: Optional[float]
    status: Optional[str]
    created_at: datetime
    scores: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True


class DashboardSummary(BaseModel):
    total_inferences: int
    templates_monitored: int
    active_alerts: int
    avg_quality_score: Optional[float]
    quality_trend: str  # "stable", "improving", "degrading"
    recent_alerts: List[AlertResponse]


# ─── Template Endpoints ───────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "api"}


@app.get("/api/templates", response_model=List[TemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PromptTemplate).order_by(PromptTemplate.created_at.desc()))
    templates = result.scalars().all()
    return [TemplateResponse(
        id=str(t.id),
        name=t.name,
        description=t.description,
        created_at=t.created_at,
    ) for t in templates]


@app.post("/api/templates", response_model=TemplateResponse, status_code=201)
async def create_template(body: TemplateCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(PromptTemplate).where(PromptTemplate.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Template already exists")

    template = PromptTemplate(name=body.name, description=body.description)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return TemplateResponse(
        id=str(template.id),
        name=template.name,
        description=template.description,
        created_at=template.created_at,
    )


# ─── Golden Reference Endpoints ──────────────────────────────────────────────

@app.get("/api/golden-references", response_model=List[GoldenReferenceResponse])
async def list_golden_references(
    template_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(GoldenReference)
    if template_id:
        query = query.where(GoldenReference.template_id == uuid.UUID(template_id))
    result = await db.execute(query.order_by(GoldenReference.created_at.desc()))
    refs = result.scalars().all()
    return [GoldenReferenceResponse(
        id=str(r.id),
        template_id=str(r.template_id),
        expected_output=r.expected_output,
        created_at=r.created_at,
    ) for r in refs]


@app.post("/api/golden-references", response_model=GoldenReferenceResponse, status_code=201)
async def create_golden_reference(
    body: GoldenReferenceCreate,
    db: AsyncSession = Depends(get_db),
):
    template = await db.get(PromptTemplate, uuid.UUID(body.template_id))
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Generate embedding async
    embedding = None
    if settings.openai_api_key:
        try:
            from app.scorer import embed_golden_reference
            import asyncio
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None, embed_golden_reference, body.expected_output
            )
        except Exception as e:
            logger.warning("golden_embed_failed", error=str(e))

    ref = GoldenReference(
        template_id=uuid.UUID(body.template_id),
        input_messages=body.input_messages,
        expected_output=body.expected_output,
        output_embedding=embedding.tolist() if embedding is not None else None,
        metadata_=body.metadata,
    )
    db.add(ref)
    await db.commit()
    await db.refresh(ref)

    return GoldenReferenceResponse(
        id=str(ref.id),
        template_id=str(ref.template_id),
        expected_output=ref.expected_output,
        created_at=ref.created_at,
    )


# ─── Metrics Endpoints ────────────────────────────────────────────────────────

@app.get("/api/metrics/time-series")
async def get_metric_time_series(
    template_id: Optional[str] = None,
    metric_name: Optional[str] = None,
    hours: int = Query(default=24, le=168),
    db: AsyncSession = Depends(get_db),
) -> List[MetricSeries]:
    """Get time-series of quality metrics."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = (
        select(
            QualityScore.metric_name,
            QualityScore.template_id,
            PromptTemplate.name.label("template_name"),
            func.date_trunc("hour", QualityScore.scored_at).label("hour"),
            func.avg(QualityScore.score).label("avg_score"),
            func.count(QualityScore.id).label("count"),
        )
        .join(PromptTemplate, QualityScore.template_id == PromptTemplate.id)
        .where(QualityScore.scored_at >= since)
        .group_by(
            QualityScore.metric_name,
            QualityScore.template_id,
            PromptTemplate.name,
            func.date_trunc("hour", QualityScore.scored_at),
        )
        .order_by(func.date_trunc("hour", QualityScore.scored_at))
    )

    if template_id:
        query = query.where(QualityScore.template_id == uuid.UUID(template_id))
    if metric_name:
        query = query.where(QualityScore.metric_name == metric_name)

    result = await db.execute(query)
    rows = result.all()

    # Group by (metric, template)
    series_map: Dict[tuple, MetricSeries] = {}
    for row in rows:
        key = (row.metric_name, str(row.template_id))
        if key not in series_map:
            series_map[key] = MetricSeries(
                metric_name=row.metric_name,
                template_name=row.template_name,
                points=[],
            )
        series_map[key].points.append(MetricPoint(
            timestamp=row.hour,
            value=round(float(row.avg_score), 4),
            sample_count=int(row.count),
        ))

    return list(series_map.values())


@app.get("/api/metrics/latest")
async def get_latest_metrics(
    template_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get the latest average score per metric per template."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    query = (
        select(
            QualityScore.metric_name,
            QualityScore.template_id,
            PromptTemplate.name.label("template_name"),
            func.avg(QualityScore.score).label("avg_score"),
            func.count(QualityScore.id).label("count"),
            func.min(QualityScore.score).label("min_score"),
            func.max(QualityScore.score).label("max_score"),
        )
        .join(PromptTemplate, QualityScore.template_id == PromptTemplate.id)
        .where(QualityScore.scored_at >= since)
        .group_by(QualityScore.metric_name, QualityScore.template_id, PromptTemplate.name)
        .order_by(QualityScore.metric_name)
    )

    if template_id:
        query = query.where(QualityScore.template_id == uuid.UUID(template_id))

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "metric_name": row.metric_name,
            "template_id": str(row.template_id),
            "template_name": row.template_name,
            "avg_score": round(float(row.avg_score), 4),
            "count": int(row.count),
            "min_score": round(float(row.min_score), 4),
            "max_score": round(float(row.max_score), 4),
        }
        for row in rows
    ]


# ─── Alert Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/alerts", response_model=List[AlertResponse])
async def list_alerts(
    template_id: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    hours: int = Query(default=48, le=720),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = (
        select(DriftAlert)
        .where(DriftAlert.created_at >= since)
        .order_by(desc(DriftAlert.created_at))
    )

    if template_id:
        query = query.where(DriftAlert.template_id == uuid.UUID(template_id))
    if acknowledged is not None:
        query = query.where(DriftAlert.acknowledged == acknowledged)

    result = await db.execute(query)
    alerts = result.scalars().all()

    return [AlertResponse(
        id=str(a.id),
        template_name=a.template_name,
        metric_name=a.metric_name,
        severity=a.severity,
        detector_type=a.detector_type,
        baseline_mean=a.baseline_mean,
        current_mean=a.current_mean,
        p_value=a.p_value,
        cusum_stat=a.cusum_stat,
        evidence=a.evidence or {},
        acknowledged=a.acknowledged,
        created_at=a.created_at,
    ) for a in alerts]


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    alert = await db.get(DriftAlert, uuid.UUID(alert_id))
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    await db.commit()
    return {"status": "acknowledged"}


# ─── Inference Log Endpoints ──────────────────────────────────────────────────

@app.get("/api/inference-logs")
async def list_inference_logs(
    template_id: Optional[str] = None,
    hours: int = Query(default=24, le=168),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = (
        select(InferenceLog)
        .where(InferenceLog.created_at >= since)
        .order_by(desc(InferenceLog.created_at))
        .limit(limit)
    )

    if template_id:
        query = query.where(InferenceLog.template_id == uuid.UUID(template_id))

    result = await db.execute(query)
    logs = result.scalars().all()

    log_ids = [log.id for log in logs]

    # Fetch scores for these logs
    scores_result = await db.execute(
        select(QualityScore).where(QualityScore.inference_log_id.in_(log_ids))
    )
    scores = scores_result.scalars().all()
    scores_by_log = {}
    for s in scores:
        lid = str(s.inference_log_id)
        if lid not in scores_by_log:
            scores_by_log[lid] = []
        scores_by_log[lid].append({
            "metric_name": s.metric_name,
            "score": round(s.score, 4),
        })

    return [
        {
            "id": str(log.id),
            "template_name": log.template_name,
            "model": log.model,
            "prompt_tokens": log.prompt_tokens,
            "completion_tokens": log.completion_tokens,
            "latency_ms": round(log.latency_ms, 1) if log.latency_ms else None,
            "status": log.status,
            "created_at": log.created_at.isoformat(),
            "scores": scores_by_log.get(str(log.id), []),
        }
        for log in logs
    ]


@app.get("/api/inference-logs/{log_id}")
async def get_inference_log(log_id: str, db: AsyncSession = Depends(get_db)):
    log = await db.get(InferenceLog, uuid.UUID(log_id))
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    scores_result = await db.execute(
        select(QualityScore).where(QualityScore.inference_log_id == log.id)
    )
    scores = scores_result.scalars().all()

    return {
        "id": str(log.id),
        "template_name": log.template_name,
        "model": log.model,
        "request_payload": log.request_payload,
        "response_payload": log.response_payload,
        "prompt_tokens": log.prompt_tokens,
        "completion_tokens": log.completion_tokens,
        "latency_ms": log.latency_ms,
        "status": log.status,
        "created_at": log.created_at.isoformat(),
        "scores": [
            {
                "metric_name": s.metric_name,
                "score": round(s.score, 4),
                "metadata": s.metadata_,
                "scored_at": s.scored_at.isoformat(),
            }
            for s in scores
        ],
    }


# ─── Dashboard Summary ────────────────────────────────────────────────────────

@app.get("/api/dashboard/summary")
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)):
    """Get high-level dashboard statistics."""
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_4h = now - timedelta(hours=4)

    # Total inferences
    total_result = await db.execute(
        select(func.count(InferenceLog.id)).where(InferenceLog.created_at >= since_24h)
    )
    total_inferences = total_result.scalar() or 0

    # Templates monitored
    templates_result = await db.execute(
        select(func.count(PromptTemplate.id))
    )
    templates_monitored = templates_result.scalar() or 0

    # Active alerts
    alerts_result = await db.execute(
        select(func.count(DriftAlert.id)).where(
            DriftAlert.acknowledged == False,
            DriftAlert.created_at >= since_24h,
        )
    )
    active_alerts = alerts_result.scalar() or 0

    # Average quality score (last 24h)
    avg_result = await db.execute(
        select(func.avg(QualityScore.score))
        .where(QualityScore.scored_at >= since_24h)
        .where(QualityScore.metric_name.like("judge_%"))
    )
    avg_quality = avg_result.scalar()

    # Quality trend
    trend = "stable"
    if avg_quality is not None:
        recent_avg_result = await db.execute(
            select(func.avg(QualityScore.score))
            .where(QualityScore.scored_at >= since_4h)
            .where(QualityScore.metric_name.like("judge_%"))
        )
        recent_avg = recent_avg_result.scalar()
        if recent_avg and avg_quality:
            delta = float(recent_avg) - float(avg_quality)
            if delta < -0.05:
                trend = "degrading"
            elif delta > 0.05:
                trend = "improving"

    # Recent alerts
    recent_alerts_result = await db.execute(
        select(DriftAlert)
        .where(DriftAlert.created_at >= since_24h)
        .order_by(desc(DriftAlert.created_at))
        .limit(5)
    )
    recent_alerts = recent_alerts_result.scalars().all()

    return {
        "total_inferences": int(total_inferences),
        "templates_monitored": int(templates_monitored),
        "active_alerts": int(active_alerts),
        "avg_quality_score": round(float(avg_quality), 3) if avg_quality else None,
        "quality_trend": trend,
        "recent_alerts": [
            {
                "id": str(a.id),
                "template_name": a.template_name,
                "metric_name": a.metric_name,
                "severity": a.severity,
                "created_at": a.created_at.isoformat(),
                "acknowledged": a.acknowledged,
            }
            for a in recent_alerts
        ],
    }


# ─── Manual Trigger Endpoints ─────────────────────────────────────────────────

@app.post("/api/trigger/drift-detection")
async def trigger_drift_detection(
    template_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger drift detection."""
    from app.worker import run_drift_detection, run_drift_detection_all

    if template_id:
        run_drift_detection.apply_async(kwargs={"template_id": template_id})
        return {"status": "triggered", "template_id": template_id}
    else:
        run_drift_detection_all.apply_async()
        return {"status": "triggered", "scope": "all"}


@app.post("/api/simulate/regression")
async def simulate_regression(
    template_name: str = "test-template",
    metric_degradation: float = 0.3,
    db: AsyncSession = Depends(get_db),
):
    """
    Simulate a quality regression by injecting synthetic scores.
    Useful for testing the detection pipeline.
    """
    from app.models import QualityScore, PromptTemplate, InferenceLog

    # Get or create template
    template_result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.name == template_name)
    )
    template = template_result.scalar_one_or_none()
    if not template:
        template = PromptTemplate(name=template_name, description="Simulated template")
        db.add(template)
        await db.flush()

    now = datetime.now(timezone.utc)
    metrics = ["judge_overall", "judge_relevance", "embedding_max_similarity"]
    injected = 0

    # Inject baseline scores (24-4 hours ago) — high quality
    for i in range(30):
        ts = now - timedelta(hours=24) + timedelta(minutes=i * 40)
        log = InferenceLog(
            template_id=template.id,
            template_name=template_name,
            request_payload={"messages": [{"role": "user", "content": "test"}]},
            response_payload={},
            model="gpt-4o-mini",
            status="scored",
            created_at=ts,
        )
        db.add(log)
        await db.flush()

        for metric in metrics:
            base_score = 0.85 + np.random.normal(0, 0.05)
            score = QualityScore(
                inference_log_id=log.id,
                template_id=template.id,
                metric_name=metric,
                score=float(np.clip(base_score, 0, 1)),
                scored_at=ts,
            )
            db.add(score)
            injected += 1

    # Inject degraded scores (last 4 hours) — low quality
    for i in range(15):
        ts = now - timedelta(hours=3) + timedelta(minutes=i * 12)
        log = InferenceLog(
            template_id=template.id,
            template_name=template_name,
            request_payload={"messages": [{"role": "user", "content": "test"}]},
            response_payload={},
            model="gpt-4o-mini",
            status="scored",
            created_at=ts,
        )
        db.add(log)
        await db.flush()

        for metric in metrics:
            degraded_score = 0.85 * (1 - metric_degradation) + np.random.normal(0, 0.04)
            score = QualityScore(
                inference_log_id=log.id,
                template_id=template.id,
                metric_name=metric,
                score=float(np.clip(degraded_score, 0, 1)),
                scored_at=ts,
            )
            db.add(score)
            injected += 1

    await db.commit()

    # Trigger detection
    from app.worker import run_drift_detection
    run_drift_detection.apply_async(kwargs={"template_id": str(template.id)})

    return {
        "status": "simulation_complete",
        "template_name": template_name,
        "scores_injected": injected,
        "metric_degradation": metric_degradation,
        "detection_triggered": True,
    }