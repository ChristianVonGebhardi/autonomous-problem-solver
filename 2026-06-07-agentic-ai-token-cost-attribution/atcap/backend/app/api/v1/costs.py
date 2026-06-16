"""Cost query and analytics endpoints."""
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from app.db.base import get_db
from app.db.models import TokenEvent, CostAggregate

router = APIRouter()


class CostSummary(BaseModel):
    total_cost_usd: float
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    call_count: int
    period_start: str
    period_end: str
    avg_cost_per_call: float


class DimensionCost(BaseModel):
    dimension: str
    total_cost_usd: float
    total_tokens: int
    call_count: int
    pct_of_total: float


class TimeSeriesPoint(BaseModel):
    timestamp: str
    cost_usd: float
    tokens: int
    call_count: int


def _period_start(period: str) -> datetime:
    now = datetime.utcnow()
    if period == "1h":
        return now - timedelta(hours=1)
    elif period == "24h":
        return now - timedelta(hours=24)
    elif period == "7d":
        return now - timedelta(days=7)
    elif period == "30d":
        return now - timedelta(days=30)
    elif period == "mtd":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return now - timedelta(days=30)


@router.get("/costs/summary", response_model=CostSummary)
async def get_cost_summary(
    period: str = Query("30d", description="1h|24h|7d|30d|mtd"),
    team: Optional[str] = None,
    feature: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated cost summary for a time period."""
    period_start = _period_start(period)
    now = datetime.utcnow()

    conditions = [TokenEvent.timestamp >= period_start]
    if team:
        conditions.append(TokenEvent.team == team)
    if feature:
        conditions.append(TokenEvent.feature == feature)

    result = await db.execute(
        select(
            func.coalesce(func.sum(TokenEvent.total_cost_usd), 0.0),
            func.coalesce(func.sum(TokenEvent.total_tokens), 0),
            func.coalesce(func.sum(TokenEvent.prompt_tokens), 0),
            func.coalesce(func.sum(TokenEvent.completion_tokens), 0),
            func.count(TokenEvent.id),
        ).where(and_(*conditions))
    )
    row = result.one()

    total_cost = float(row[0])
    call_count = int(row[4])
    avg_cost = total_cost / call_count if call_count > 0 else 0.0

    return CostSummary(
        total_cost_usd=round(total_cost, 4),
        total_tokens=int(row[2]) + int(row[3]),
        prompt_tokens=int(row[2]),
        completion_tokens=int(row[3]),
        call_count=call_count,
        period_start=period_start.isoformat(),
        period_end=now.isoformat(),
        avg_cost_per_call=round(avg_cost, 6),
    )


@router.get("/costs/by-team", response_model=List[DimensionCost])
async def get_costs_by_team(
    period: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
):
    """Get cost breakdown by team."""
    return await _get_costs_by_dimension(db, period, TokenEvent.team, "team")


@router.get("/costs/by-feature", response_model=List[DimensionCost])
async def get_costs_by_feature(
    period: str = Query("30d"),
    team: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get cost breakdown by feature."""
    return await _get_costs_by_dimension(db, period, TokenEvent.feature, "feature", team_filter=team)


@router.get("/costs/by-model", response_model=List[DimensionCost])
async def get_costs_by_model(
    period: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
):
    """Get cost breakdown by LLM model."""
    return await _get_costs_by_dimension(db, period, TokenEvent.model, "model")


@router.get("/costs/by-workflow", response_model=List[DimensionCost])
async def get_costs_by_workflow(
    period: str = Query("30d"),
    team: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get cost breakdown by workflow ID."""
    return await _get_costs_by_dimension(db, period, TokenEvent.workflow_id, "workflow", team_filter=team)


@router.get("/costs/timeseries", response_model=List[TimeSeriesPoint])
async def get_cost_timeseries(
    period: str = Query("7d"),
    granularity: str = Query("1h", description="1h|6h|1d"),
    team: Optional[str] = None,
    feature: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get cost time series data for charting."""
    period_start = _period_start(period)

    # For SQLite, we use strftime; for production use date_trunc
    if granularity == "1h":
        fmt = "%Y-%m-%d %H:00:00"
    elif granularity == "6h":
        fmt = "%Y-%m-%d %H:00:00"  # simplification
    else:
        fmt = "%Y-%m-%d 00:00:00"

    conditions = [TokenEvent.timestamp >= period_start]
    if team:
        conditions.append(TokenEvent.team == team)
    if feature:
        conditions.append(TokenEvent.feature == feature)

    from sqlalchemy import text
    result = await db.execute(
        select(
            func.strftime(fmt, TokenEvent.timestamp).label("ts"),
            func.sum(TokenEvent.total_cost_usd).label("cost"),
            func.sum(TokenEvent.total_tokens).label("tokens"),
            func.count(TokenEvent.id).label("calls"),
        ).where(and_(*conditions))
        .group_by(text("ts"))
        .order_by(text("ts"))
    )

    points = []
    for row in result.all():
        points.append(TimeSeriesPoint(
            timestamp=str(row.ts),
            cost_usd=round(float(row.cost or 0), 6),
            tokens=int(row.tokens or 0),
            call_count=int(row.calls or 0),
        ))

    return points


@router.get("/costs/top-events")
async def get_top_events(
    period: str = Query("24h"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get the most expensive individual LLM calls."""
    period_start = _period_start(period)

    result = await db.execute(
        select(TokenEvent)
        .where(TokenEvent.timestamp >= period_start)
        .order_by(desc(TokenEvent.total_cost_usd))
        .limit(limit)
    )

    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "team": e.team,
            "feature": e.feature,
            "model": e.model,
            "total_cost_usd": e.total_cost_usd,
            "total_tokens": e.total_tokens,
            "workflow_id": e.workflow_id,
            "business_entity_id": e.business_entity_id,
            "latency_ms": e.latency_ms,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events
    ]


async def _get_costs_by_dimension(
    db: AsyncSession,
    period: str,
    dim_col,
    dim_name: str,
    team_filter: Optional[str] = None,
) -> List[DimensionCost]:
    period_start = _period_start(period)

    conditions = [TokenEvent.timestamp >= period_start]
    if team_filter:
        conditions.append(TokenEvent.team == team_filter)

    result = await db.execute(
        select(
            dim_col.label("dim"),
            func.sum(TokenEvent.total_cost_usd).label("cost"),
            func.sum(TokenEvent.total_tokens).label("tokens"),
            func.count(TokenEvent.id).label("calls"),
        ).where(and_(*conditions))
        .group_by(dim_col)
        .order_by(desc("cost"))
    )

    rows = result.all()
    if not rows:
        return []

    total = sum(float(r.cost or 0) for r in rows)

    return [
        DimensionCost(
            dimension=str(r.dim) if r.dim else "unknown",
            total_cost_usd=round(float(r.cost or 0), 4),
            total_tokens=int(r.tokens or 0),
            call_count=int(r.calls or 0),
            pct_of_total=round((float(r.cost or 0) / total * 100) if total > 0 else 0, 1),
        )
        for r in rows
    ]