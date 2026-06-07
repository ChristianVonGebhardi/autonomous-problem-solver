"""Pricing catalog endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.base import get_db
from app.db.models import PricingCatalog
from app.services.pricing import invalidate_cache
from datetime import datetime
import uuid

router = APIRouter()


class PricingResponse(BaseModel):
    id: str
    provider: str
    model: str
    prompt_cost_per_1k_tokens: float
    completion_cost_per_1k_tokens: float
    effective_from: datetime
    is_current: bool

    class Config:
        from_attributes = True


class PricingCreate(BaseModel):
    provider: str
    model: str
    prompt_cost_per_1k_tokens: float
    completion_cost_per_1k_tokens: float


@router.get("/pricing", response_model=List[PricingResponse])
async def list_pricing(db: AsyncSession = Depends(get_db)):
    """List all current pricing entries."""
    result = await db.execute(
        select(PricingCatalog)
        .where(PricingCatalog.is_current == True)
        .order_by(PricingCatalog.provider, PricingCatalog.model)
    )
    return result.scalars().all()


@router.post("/pricing", response_model=PricingResponse, status_code=201)
async def create_pricing(
    req: PricingCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add or update a pricing entry."""
    # Expire existing entry for this model
    existing = await db.execute(
        select(PricingCatalog).where(
            PricingCatalog.model == req.model,
            PricingCatalog.is_current == True
        )
    )
    for old in existing.scalars().all():
        old.is_current = False
        old.effective_to = datetime.utcnow()

    entry = PricingCatalog(
        id=str(uuid.uuid4()),
        provider=req.provider,
        model=req.model,
        prompt_cost_per_1k_tokens=req.prompt_cost_per_1k_tokens,
        completion_cost_per_1k_tokens=req.completion_cost_per_1k_tokens,
        effective_from=datetime.utcnow(),
        is_current=True,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    invalidate_cache()

    return entry