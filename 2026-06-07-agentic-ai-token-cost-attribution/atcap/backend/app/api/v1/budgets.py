"""Budget policy management endpoints."""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.db.base import get_db
from app.db.models import BudgetPolicy, TokenEvent
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


@router.post("/budgets/evaluate")
async def trigger_evaluation(db: AsyncSession = Depends(get_db)):
    """Manually trigger budget policy evaluation."""
    await evaluate_budget_policies(db)
    return {"evaluated": True}