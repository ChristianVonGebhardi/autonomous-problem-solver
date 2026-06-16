"""ROI and business value correlation endpoints."""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from app.db.base import get_db
from app.db.models import ROIRecord, ValueEvent
from app.services.cost_processor import compute_roi_records
from app.services.value_ingestion import create_value_event_from_webhook

router = APIRouter()


class ValueEventCreate(BaseModel):
    source: str
    event_type: str
    team: Optional[str] = None
    feature: Optional[str] = None
    business_entity_id: Optional[str] = None
    value_points: float = 1.0
    value_usd: Optional[float] = None
    title: Optional[str] = None
    url: Optional[str] = None
    extra: Optional[dict] = None


class ROIResponse(BaseModel):
    team: Optional[str]
    feature: Optional[str]
    period_start: datetime
    period_end: datetime
    total_cost_usd: float
    total_tokens: int
    call_count: int
    value_events_count: int
    value_points: float
    value_usd: Optional[float]
    cost_per_value_point: Optional[float]
    roi_ratio: Optional[float]
    roi_label: str


@router.get("/roi", response_model=List[ROIResponse])
async def get_roi_records(
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get latest ROI correlation records."""
    result = await db.execute(
        select(ROIRecord)
        .order_by(desc(ROIRecord.computed_at))
        .limit(limit)
    )
    records = result.scalars().all()

    return [
        ROIResponse(
            team=r.team,
            feature=r.feature,
            period_start=r.period_start,
            period_end=r.period_end,
            total_cost_usd=r.total_cost_usd,
            total_tokens=r.total_tokens,
            call_count=r.call_count,
            value_events_count=r.value_events_count,
            value_points=r.value_points,
            value_usd=r.value_usd,
            cost_per_value_point=r.cost_per_value_point,
            roi_ratio=r.roi_ratio,
            roi_label=_roi_label(r.roi_ratio),
        )
        for r in records
    ]


@router.post("/roi/compute")
async def trigger_roi_computation(db: AsyncSession = Depends(get_db)):
    """Manually trigger ROI computation."""
    await compute_roi_records(db)
    return {"computed": True}


@router.get("/value-events")
async def list_value_events(
    period: str = Query("30d"),
    team: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List business value events."""
    period_start = _period_start(period)

    conditions = [ValueEvent.timestamp >= period_start]
    if team:
        conditions.append(ValueEvent.team == team)
    if source:
        conditions.append(ValueEvent.source == source)

    result = await db.execute(
        select(ValueEvent)
        .where(and_(*conditions))
        .order_by(desc(ValueEvent.timestamp))
        .limit(limit)
    )
    events = result.scalars().all()

    return [
        {
            "id": e.id,
            "source": e.source,
            "event_type": e.event_type,
            "team": e.team,
            "feature": e.feature,
            "business_entity_id": e.business_entity_id,
            "value_points": e.value_points,
            "value_usd": e.value_usd,
            "title": e.title,
            "url": e.url,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events
    ]


@router.post("/value-events", status_code=201)
async def create_value_event(
    req: ValueEventCreate,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a business value event (PR, ticket, revenue signal)."""
    event = await create_value_event_from_webhook(db, req.dict())
    return {"id": event.id, "created": True}


def _period_start(period: str) -> datetime:
    now = datetime.utcnow()
    if period == "1h":
        return now - timedelta(hours=1)
    elif period == "24h":
        return now - timedelta(hours=24)
    elif period == "7d":
        return now - timedelta(days=7)
    else:
        return now - timedelta(days=30)


def _roi_label(roi_ratio: Optional[float]) -> str:
    if roi_ratio is None:
        return "unknown"
    if roi_ratio >= 10:
        return "excellent"
    elif roi_ratio >= 3:
        return "good"
    elif roi_ratio >= 1:
        return "break-even"
    else:
        return "negative"