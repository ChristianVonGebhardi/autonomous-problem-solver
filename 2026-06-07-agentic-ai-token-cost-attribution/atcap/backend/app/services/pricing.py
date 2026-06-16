"""Pricing catalog service — computes costs from token counts."""
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import PricingCatalog

# In-memory cache to avoid repeated DB hits
_pricing_cache: Dict[str, Dict] = {}


async def get_pricing(model: str, db: AsyncSession) -> Optional[Dict]:
    """Fetch current pricing for a model."""
    if model in _pricing_cache:
        return _pricing_cache[model]

    result = await db.execute(
        select(PricingCatalog).where(
            PricingCatalog.model == model,
            PricingCatalog.is_current == True
        ).limit(1)
    )
    catalog = result.scalar_one_or_none()

    if catalog:
        pricing = {
            "provider": catalog.provider,
            "model": catalog.model,
            "prompt_cost_per_1k": catalog.prompt_cost_per_1k_tokens,
            "completion_cost_per_1k": catalog.completion_cost_per_1k_tokens,
        }
        _pricing_cache[model] = pricing
        return pricing
    return None


def compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    prompt_cost_per_1k: float,
    completion_cost_per_1k: float,
) -> Dict[str, float]:
    """Compute cost from token counts and per-1k rates."""
    prompt_cost = (prompt_tokens / 1000.0) * prompt_cost_per_1k
    completion_cost = (completion_tokens / 1000.0) * completion_cost_per_1k
    return {
        "prompt_cost_usd": round(prompt_cost, 8),
        "completion_cost_usd": round(completion_cost, 8),
        "total_cost_usd": round(prompt_cost + completion_cost, 8),
    }


def invalidate_cache():
    """Invalidate pricing cache (call after catalog update)."""
    global _pricing_cache
    _pricing_cache = {}