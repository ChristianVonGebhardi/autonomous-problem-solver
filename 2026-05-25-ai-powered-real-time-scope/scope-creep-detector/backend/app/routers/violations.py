from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, Violation, ViolationStatus
from app.schemas import ViolationOut
from app.auth import get_current_user

router = APIRouter(prefix="/api/violations", tags=["violations"])


@router.get("/", response_model=List[ViolationOut])
async def list_violations(
    contract_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Violation).where(Violation.owner_id == current_user.id)
    
    if contract_id:
        query = query.where(Violation.contract_id == contract_id)
    if status:
        query = query.where(Violation.status == status)
    
    query = query.order_by(Violation.created_at.desc())
    
    result = await db.execute(query)
    violations = result.scalars().all()
    return [ViolationOut.model_validate(v) for v in violations]


@router.get("/{violation_id}", response_model=ViolationOut)
async def get_violation(
    violation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Violation).where(
            Violation.id == violation_id,
            Violation.owner_id == current_user.id,
        )
    )
    violation = result.scalar_one_or_none()
    if not violation:
        raise HTTPException(status_code=404, detail="Violation not found")
    return ViolationOut.model_validate(violation)


@router.post("/{violation_id}/dismiss", response_model=ViolationOut)
async def dismiss_violation(
    violation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Violation).where(
            Violation.id == violation_id,
            Violation.owner_id == current_user.id,
        )
    )
    violation = result.scalar_one_or_none()
    if not violation:
        raise HTTPException(status_code=404, detail="Violation not found")
    
    violation.status = ViolationStatus.DISMISSED
    await db.commit()
    await db.refresh(violation)
    return ViolationOut.model_validate(violation)