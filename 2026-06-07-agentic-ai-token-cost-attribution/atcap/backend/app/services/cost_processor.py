"""
Background cost processor — enriches raw token events with pricing,
computes windowed aggregates, and evaluates budget policies.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.db.base import AsyncSessionLocal
from app.db.models import TokenEvent, CostAggregate, BudgetPolicy, BudgetAlert, ROIRecord, ValueEvent
from app.services.pricing import get_pricing, compute_cost
from app.services.alerting import send_budget_alert

logger = logging.getLogger(__name__)


async def process_token_event(event: TokenEvent, db: AsyncSession) -> TokenEvent:
    """Enrich a token event with cost data using the pricing catalog."""
    pricing = await get_pricing(event.model, db)
    if pricing:
        costs = compute_cost(
            event.prompt_tokens,
            event.completion_tokens,
            pricing["prompt_cost_per_1k"],
            pricing["completion_cost_per_1k"],
        )
        event.prompt_cost_usd = costs["prompt_cost_usd"]
        event.completion_cost_usd = costs["completion_cost_usd"]
        event.total_cost_usd = costs["total_cost_usd"]
    else:
        # Unknown model — estimate at $0.01/1k tokens
        fallback_rate = 0.01
        event.prompt_cost_usd = (event.prompt_tokens / 1000.0) * fallback_rate
        event.completion_cost_usd = (event.completion_tokens / 1000.0) * fallback_rate
        event.total_cost_usd = event.prompt_cost_usd + event.completion_cost_usd
        logger.warning(f"Unknown model '{event.model}', using fallback pricing")

    return event


async def compute_windowed_aggregates(
    window_minutes: int = 15,
    db: Optional[AsyncSession] = None,
):
    """Compute rolling window aggregates over token events."""
    close_db = False
    if db is None:
        db = AsyncSessionLocal()
        close_db = True

    try:
        window_end = datetime.utcnow()
        window_start = window_end - timedelta(minutes=window_minutes)

        # Aggregate by dimension type
        dimensions = [
            ("team", TokenEvent.team),
            ("feature", TokenEvent.feature),
            ("model", TokenEvent.model),
        ]

        for dim_type, dim_col in dimensions:
            result = await db.execute(
                select(
                    dim_col.label("dim_value"),
                    func.sum(TokenEvent.total_cost_usd).label("total_cost"),
                    func.sum(TokenEvent.total_tokens).label("total_tokens"),
                    func.sum(TokenEvent.prompt_tokens).label("prompt_tokens"),
                    func.sum(TokenEvent.completion_tokens).label("completion_tokens"),
                    func.count(TokenEvent.id).label("call_count"),
                    func.avg(TokenEvent.latency_ms).label("avg_latency"),
                ).where(
                    and_(
                        TokenEvent.timestamp >= window_start,
                        TokenEvent.timestamp <= window_end,
                    )
                ).group_by(dim_col)
            )

            rows = result.all()
            for row in rows:
                agg = CostAggregate(
                    window_start=window_start,
                    window_end=window_end,
                    window_size_seconds=window_minutes * 60,
                    dimension_type=dim_type,
                    dimension_value=str(row.dim_value),
                    total_cost_usd=float(row.total_cost or 0),
                    total_tokens=int(row.total_tokens or 0),
                    prompt_tokens=int(row.prompt_tokens or 0),
                    completion_tokens=int(row.completion_tokens or 0),
                    call_count=int(row.call_count or 0),
                    avg_latency_ms=float(row.avg_latency) if row.avg_latency else None,
                    computed_at=datetime.utcnow(),
                )
                db.add(agg)

        await db.commit()
        logger.debug(f"Computed aggregates for window {window_start} - {window_end}")

    finally:
        if close_db:
            await db.close()


async def evaluate_budget_policies(db: Optional[AsyncSession] = None):
    """Check current spend against budget policies and trigger alerts."""
    close_db = False
    if db is None:
        db = AsyncSessionLocal()
        close_db = True

    try:
        policies_result = await db.execute(
            select(BudgetPolicy).where(BudgetPolicy.is_active == True)
        )
        policies = policies_result.scalars().all()

        now = datetime.utcnow()

        for policy in policies:
            period_start = _get_period_start(now, policy.period)

            # Calculate current spend for this policy's scope
            query = select(func.sum(TokenEvent.total_cost_usd)).where(
                TokenEvent.timestamp >= period_start
            )

            if policy.dimension_type == "team" and policy.dimension_value:
                query = query.where(TokenEvent.team == policy.dimension_value)
            elif policy.dimension_type == "feature" and policy.dimension_value:
                query = query.where(TokenEvent.feature == policy.dimension_value)
            elif policy.dimension_type == "model" and policy.dimension_value:
                query = query.where(TokenEvent.model == policy.dimension_value)
            # global = no additional filter

            result = await db.execute(query)
            current_spend = float(result.scalar() or 0.0)
            spend_pct = (current_spend / policy.budget_usd) * 100

            # Determine alert level
            alert_level = None
            if spend_pct >= policy.critical_threshold_pct:
                alert_level = "critical"
            elif spend_pct >= policy.warn_threshold_pct:
                alert_level = "warn"

            if alert_level:
                # Check if we already fired this alert recently (last 1 hour)
                recent_alert = await db.execute(
                    select(BudgetAlert).where(
                        and_(
                            BudgetAlert.policy_id == policy.id,
                            BudgetAlert.alert_level == alert_level,
                            BudgetAlert.triggered_at >= now - timedelta(hours=1),
                        )
                    ).limit(1)
                )
                if not recent_alert.scalar_one_or_none():
                    message = (
                        f"Budget alert ({alert_level.upper()}): "
                        f"{policy.name} has consumed ${current_spend:.2f} "
                        f"({spend_pct:.1f}%) of ${policy.budget_usd:.2f} {policy.period} budget"
                    )
                    alert = BudgetAlert(
                        policy_id=policy.id,
                        alert_level=alert_level,
                        current_spend_usd=current_spend,
                        budget_usd=policy.budget_usd,
                        spend_pct=spend_pct,
                        message=message,
                    )
                    db.add(alert)
                    await db.flush()

                    # Send Slack notification
                    notified = await send_budget_alert(
                        policy_name=policy.name,
                        dimension_type=policy.dimension_type,
                        dimension_value=policy.dimension_value,
                        current_spend=current_spend,
                        budget=policy.budget_usd,
                        spend_pct=spend_pct,
                        alert_level=alert_level,
                        period=policy.period,
                    )
                    alert.notified_slack = notified
                    logger.info(f"Budget alert triggered: {message}")

        await db.commit()

    finally:
        if close_db:
            await db.close()


async def compute_roi_records(db: Optional[AsyncSession] = None):
    """Correlate cost and value events to produce ROI records."""
    close_db = False
    if db is None:
        db = AsyncSessionLocal()
        close_db = True

    try:
        now = datetime.utcnow()
        period_start = now - timedelta(days=30)

        # Get distinct teams with cost data
        teams_result = await db.execute(
            select(TokenEvent.team).where(
                TokenEvent.timestamp >= period_start
            ).distinct()
        )
        teams = [r[0] for r in teams_result.all()]

        for team in teams:
            # Cost side
            cost_result = await db.execute(
                select(
                    func.sum(TokenEvent.total_cost_usd),
                    func.sum(TokenEvent.total_tokens),
                    func.count(TokenEvent.id),
                ).where(
                    and_(
                        TokenEvent.team == team,
                        TokenEvent.timestamp >= period_start,
                    )
                )
            )
            cost_row = cost_result.one()
            total_cost = float(cost_row[0] or 0)
            total_tokens = int(cost_row[1] or 0)
            call_count = int(cost_row[2] or 0)

            # Value side
            value_result = await db.execute(
                select(
                    func.count(ValueEvent.id),
                    func.sum(ValueEvent.value_points),
                    func.sum(ValueEvent.value_usd),
                ).where(
                    and_(
                        ValueEvent.team == team,
                        ValueEvent.timestamp >= period_start,
                    )
                )
            )
            value_row = value_result.one()
            value_count = int(value_row[0] or 0)
            value_points = float(value_row[1] or 0)
            value_usd = float(value_row[2] or 0) if value_row[2] else None

            # Compute ROI
            cost_per_value_point = (total_cost / value_points) if value_points > 0 else None
            roi_ratio = (value_usd / total_cost) if (value_usd and total_cost > 0) else None

            roi = ROIRecord(
                period_start=period_start,
                period_end=now,
                team=team,
                total_cost_usd=total_cost,
                total_tokens=total_tokens,
                call_count=call_count,
                value_events_count=value_count,
                value_points=value_points,
                value_usd=value_usd,
                cost_per_value_point=cost_per_value_point,
                roi_ratio=roi_ratio,
                computed_at=now,
            )
            db.add(roi)

        await db.commit()

    finally:
        if close_db:
            await db.close()


def _get_period_start(now: datetime, period: str) -> datetime:
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        days_since_monday = now.weekday()
        return (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:  # monthly
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)