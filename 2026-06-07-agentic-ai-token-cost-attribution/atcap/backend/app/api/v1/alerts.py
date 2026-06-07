"""Alert testing and notification endpoints."""
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import BudgetAlert, BudgetPolicy
from app.services.alerting import send_test_alert

router = APIRouter()


class AlertResponse(BaseModel):
    id: str
    policy_id: str
    policy_name: str
    alert_level: str
    current_spend_usd: float
    budget_usd: float
    spend_pct: float
    message: str | None
    notified_slack: bool
    acknowledged: bool
    triggered_at: datetime

    class Config:
        from_attributes = True


@router.post("/alerts/test")
async def test_alert():
    """Send a test alert to verify Slack integration."""
    result = await send_test_alert()
    return result


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