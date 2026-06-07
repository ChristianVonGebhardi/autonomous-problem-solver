"""Budget policy management endpoints."""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from app.db.base import get_db
from app.db.models import BudgetPolicy, BudgetAlert, TokenEvent
from app.services.cost_processor import evaluate_budget_policies
import uuid

router = APIRouter()


class BudgetPolicyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    dimension_type: str = Field(..., pattern="^(team|feature|model|global)$")
    dimension_value: Optional[str] = None
    budget_usd: float = Field(..., gt=0)
    period: str = Field("monthly", pattern="^(daily|weekly|monthly)$")
    warn_threshold_pct: float = Field(80.0, ge=0, le=100)
    critical_threshold_pct: float = Field(95.0, ge=0, le=100)


class BudgetPolicyResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    dimension_type: str
    dimension_value: Optional[str]
    budget_usd: float
    period: str
    warn_threshold_pct: float
    critical_threshold_pct: float
    is_active: bool
    current_spend_usd: float = 0.0
    spend_pct: float = 0.0

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    id: str
    policy_id: str
    policy_name: str
    alert_level: str
    current_spend_usd: float
    budget_usd: float
    spend_pct: float
    message: Optional[str]
    notified_slack: bool
    acknowledged: bool
    triggered_at: datetime

    class Config:
        from_attributes = True


def _period_start_for(period: str) -> datetime:
    now = datetime.utcnow()
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        days = now.weekday()
        return (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/budgets", response_model=List[BudgetPolicyResponse])
async def list_budgets(db: AsyncSession = Depends(get_db)):
    """List all budget policies with current spend."""
    result = await db.execute(
        select(BudgetPolicy).where(BudgetPolicy.is_active == True).order_by(BudgetPolicy.created_at)
    )
    policies = result.scalars().all()

    responses = []
    for policy in policies:
        period_start = _period_start_for(policy.period)

        query = select(func.coalesce(func.sum(TokenEvent.total_cost_usd), 0.0)).where(
            TokenEvent.timestamp >= period_start
        )
        if policy.dimension_type == "team" and policy.dimension_value:
            query = query.where(TokenEvent.team == policy.dimension_value)
        elif policy.dimension_type == "feature" and policy.dimension_value:
            query = query.where(TokenEvent.feature == policy.dimension_value)
        elif policy.dimension_type == "model" and policy.dimension_value:
            query = query.where(TokenEvent.model == policy.dimension_value)

        spend_result = await db.execute(query)
        current_spend = float(spend_result.scalar() or 0)
        spend_pct = (current_spend / policy.budget_usd) * 100 if policy.budget_usd > 0 else 0

        responses.append(BudgetPolicyResponse(
            id=policy.id,
            name=policy.name,
            description=policy.description,
            dimension_type=policy.dimension_type,
            dimension_value=policy.dimension_value,
            budget_usd=policy.budget_usd,
            period=policy.period,
            warn_threshold_pct=policy.warn_threshold_pct,
            critical_threshold_pct=policy.critical_threshold_pct,
            is_active=policy.is_active,
            current_spend_usd=round(current_spend, 4),
            spend_pct=round(spend_pct, 1),
        ))

    return responses


@router.post("/budgets", response_model=BudgetPolicyResponse, status_code=201)
async def create_budget(
    req: BudgetPolicyCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new budget policy."""
    policy = BudgetPolicy(
        id=str(uuid.uuid4()),
        name=req.name,
        description=req.description,
        dimension_type=req.dimension_type,
        dimension_value=req.dimension_value,
        budget_usd=req.budget_usd,
        period=req.period,
        warn_threshold_pct=req.warn_threshold_pct,
        critical_threshold_pct=req.critical_threshold_pct,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)

    return BudgetPolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        dimension_type=policy.dimension_type,
        dimension_value=policy.dimension_value,
        budget_usd=policy.budget_usd,
        period=policy.period,
        warn_threshold_pct=policy.warn_threshold_pct,
        critical_threshold_pct=policy.critical_threshold_pct,
        is_active=policy.is_active,
        current_spend_usd=0.0,
        spend_pct=0.0,
    )


@router.put("/budgets/{policy_id}")
async def update_budget(
    policy_id: str,
    req: BudgetPolicyCreate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing budget policy."""
    result = await db.execute(select(BudgetPolicy).where(BudgetPolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Budget policy not found")

    policy.name = req.name
    policy.description = req.description
    policy.budget_usd = req.budget_usd
    policy.warn_threshold_pct = req.warn_threshold_pct
    policy.critical_threshold_pct = req.critical_threshold_pct
    policy.updated_at = datetime.utcnow()

    await db.commit()
    return {"id": policy_id, "updated": True}


@router.delete("/budgets/{policy_id}")
async def delete_budget(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a budget policy."""
    result = await db.execute(select(BudgetPolicy).where(BudgetPolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Budget policy not found")

    policy.is_active = False
    await db.commit()
    return {"id": policy_id, "deleted": True}


@router.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    unacknowledged_only: bool = True,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List triggered budget alerts."""
    query = (
        select(BudgetAlert, BudgetPolicy.name)
        .join(BudgetPolicy, BudgetAlert.policy_id == BudgetPolicy.id)
        .order_by(desc(BudgetAlert.triggered_at))
        .limit(limit)
    )
    if unacknowledged_only:
        query = query.where(BudgetAlert.acknowledged == False)

    result = await db.execute(query)
    rows = result.all()

    return [
        AlertResponse(
            id=row[0].id,
            policy_id=row[0].policy_id,
            policy_name=row[1],
            alert_level=row[0].alert_level,
            current_spend_usd=row[0].current_spend_usd,
            budget_usd=row[0].budget_usd,
            spend_pct=row[0].spend_pct,
            message=row[0].message,
            notified_slack=row[0].notified_slack,
            acknowledged=row[0].acknowledged,
            triggered_at=row[0].triggered_at,
        )
        for row in rows
    ]


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge a budget alert."""
    result = await db.execute(select(BudgetAlert).where(BudgetAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = True
    await db.commit()
    return {"id": alert_id, "acknowledged": True}


@router.post("/budgets/evaluate")
async def trigger_evaluation(db: AsyncSession = Depends(get_db)):
    """Manually trigger budget policy evaluation."""
    await evaluate_budget_policies(db)
    return {"evaluated": True}