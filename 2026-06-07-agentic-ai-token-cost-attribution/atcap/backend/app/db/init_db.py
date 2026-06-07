"""Initialize the database schema and seed pricing catalog."""
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime

from sqlalchemy import text
from app.db.base import Base, engine
from app.db.models import PricingCatalog, BudgetPolicy


PRICING_DATA = [
    # OpenAI
    {"provider": "openai", "model": "gpt-4o", "prompt": 0.005, "completion": 0.015},
    {"provider": "openai", "model": "gpt-4o-mini", "prompt": 0.00015, "completion": 0.0006},
    {"provider": "openai", "model": "gpt-4-turbo", "prompt": 0.01, "completion": 0.03},
    {"provider": "openai", "model": "gpt-3.5-turbo", "prompt": 0.0005, "completion": 0.0015},
    {"provider": "openai", "model": "o1", "prompt": 0.015, "completion": 0.060},
    {"provider": "openai", "model": "o1-mini", "prompt": 0.003, "completion": 0.012},
    # Anthropic
    {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022", "prompt": 0.003, "completion": 0.015},
    {"provider": "anthropic", "model": "claude-3-opus-20240229", "prompt": 0.015, "completion": 0.075},
    {"provider": "anthropic", "model": "claude-3-haiku-20240307", "prompt": 0.00025, "completion": 0.00125},
    # Google
    {"provider": "google", "model": "gemini-1.5-pro", "prompt": 0.00125, "completion": 0.005},
    {"provider": "google", "model": "gemini-1.5-flash", "prompt": 0.000075, "completion": 0.0003},
    {"provider": "google", "model": "gemini-2.0-flash", "prompt": 0.0001, "completion": 0.0004},
    # AWS Bedrock (Claude via Bedrock)
    {"provider": "bedrock", "model": "anthropic.claude-3-sonnet-20240229-v1:0", "prompt": 0.003, "completion": 0.015},
    {"provider": "bedrock", "model": "amazon.titan-text-express-v1", "prompt": 0.0002, "completion": 0.0006},
]

DEFAULT_POLICIES = [
    {
        "name": "Global Monthly Budget",
        "description": "Company-wide monthly AI spend limit",
        "dimension_type": "global",
        "dimension_value": None,
        "budget_usd": 10000.0,
        "period": "monthly",
        "warn_threshold_pct": 75.0,
        "critical_threshold_pct": 90.0,
    },
    {
        "name": "Platform Team Monthly",
        "description": "Platform team monthly AI budget",
        "dimension_type": "team",
        "dimension_value": "platform",
        "budget_usd": 2000.0,
        "period": "monthly",
        "warn_threshold_pct": 80.0,
        "critical_threshold_pct": 95.0,
    },
    {
        "name": "Search Feature Budget",
        "description": "AI-powered search feature monthly budget",
        "dimension_type": "feature",
        "dimension_value": "ai-search",
        "budget_usd": 500.0,
        "period": "monthly",
        "warn_threshold_pct": 70.0,
        "critical_threshold_pct": 90.0,
    },
]


async def init_db():
    """Create all tables and seed initial data."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.base import AsyncSessionLocal
    import uuid

    async with AsyncSessionLocal() as session:
        # Seed pricing catalog
        from sqlalchemy import select
        result = await session.execute(select(PricingCatalog).limit(1))
        if not result.scalar_one_or_none():
            for item in PRICING_DATA:
                catalog_entry = PricingCatalog(
                    id=str(uuid.uuid4()),
                    provider=item["provider"],
                    model=item["model"],
                    prompt_cost_per_1k_tokens=item["prompt"],
                    completion_cost_per_1k_tokens=item["completion"],
                    effective_from=datetime.utcnow(),
                    is_current=True,
                )
                session.add(catalog_entry)

        # Seed default budget policies
        result = await session.execute(select(BudgetPolicy).limit(1))
        if not result.scalar_one_or_none():
            for policy_data in DEFAULT_POLICIES:
                policy = BudgetPolicy(
                    id=str(uuid.uuid4()),
                    **policy_data
                )
                session.add(policy)

        await session.commit()

    print("✅ Database initialized with pricing catalog and default policies")


if __name__ == "__main__":
    asyncio.run(init_db())