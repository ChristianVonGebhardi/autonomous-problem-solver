from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta

from app.database import get_db
from app.models import User, Contract, Message, Violation, ChangeOrder, ChangeOrderStatus, ViolationStatus
from app.schemas import DashboardStats
from app.auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    
    # Contracts
    total_contracts_r = await db.execute(
        select(func.count(Contract.id)).where(Contract.owner_id == user_id)
    )
    total_contracts = total_contracts_r.scalar() or 0
    
    active_contracts_r = await db.execute(
        select(func.count(Contract.id)).where(
            and_(Contract.owner_id == user_id, Contract.status == "active")
        )
    )
    active_contracts = active_contracts_r.scalar() or 0
    
    # Violations
    total_violations_r = await db.execute(
        select(func.count(Violation.id)).where(Violation.owner_id == user_id)
    )
    total_violations = total_violations_r.scalar() or 0
    
    pending_violations_r = await db.execute(
        select(func.count(Violation.id)).where(
            and_(Violation.owner_id == user_id, Violation.status == ViolationStatus.PENDING)
        )
    )
    pending_violations = pending_violations_r.scalar() or 0
    
    # Change orders
    total_co_r = await db.execute(
        select(func.count(ChangeOrder.id)).where(ChangeOrder.owner_id == user_id)
    )
    total_change_orders = total_co_r.scalar() or 0
    
    approved_co_r = await db.execute(
        select(func.count(ChangeOrder.id)).where(
            and_(
                ChangeOrder.owner_id == user_id,
                ChangeOrder.status.in_([ChangeOrderStatus.APPROVED, ChangeOrderStatus.SENT, ChangeOrderStatus.ACCEPTED])
            )
        )
    )
    approved_change_orders = approved_co_r.scalar() or 0
    
    # Revenue metrics
    recovered_r = await db.execute(
        select(func.coalesce(func.sum(ChangeOrder.total_cost), 0)).where(
            and_(
                ChangeOrder.owner_id == user_id,
                ChangeOrder.status.in_([ChangeOrderStatus.APPROVED, ChangeOrderStatus.SENT, ChangeOrderStatus.ACCEPTED])
            )
        )
    )
    recovered_revenue = float(recovered_r.scalar() or 0)
    
    potential_r = await db.execute(
        select(func.coalesce(func.sum(ChangeOrder.total_cost), 0)).where(
            ChangeOrder.owner_id == user_id
        )
    )
    potential_revenue = float(potential_r.scalar() or 0)
    
    # Monthly (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    monthly_r = await db.execute(
        select(func.coalesce(func.sum(ChangeOrder.total_cost), 0)).where(
            and_(
                ChangeOrder.owner_id == user_id,
                ChangeOrder.created_at >= thirty_days_ago,
                ChangeOrder.status.in_([ChangeOrderStatus.APPROVED, ChangeOrderStatus.SENT, ChangeOrderStatus.ACCEPTED])
            )
        )
    )
    monthly_recovered = float(monthly_r.scalar() or 0)
    
    return DashboardStats(
        total_contracts=total_contracts,
        active_contracts=active_contracts,
        total_violations=total_violations,
        pending_violations=pending_violations,
        total_change_orders=total_change_orders,
        approved_change_orders=approved_change_orders,
        recovered_revenue=recovered_revenue,
        potential_revenue=potential_revenue,
        monthly_recovered=monthly_recovered,
    )