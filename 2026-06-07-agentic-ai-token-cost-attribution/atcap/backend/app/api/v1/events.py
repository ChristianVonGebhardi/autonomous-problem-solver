"""Token event ingestion endpoints."""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import get_db
from app.db.models import TokenEvent
from app.services.cost_processor import process_token_event
import uuid

router = APIRouter()


class TokenEventRequest(BaseModel):
    # Tracing
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    # Attribution
    team: str = Field(..., min_length=1)
    feature: str = Field(..., min_length=1)
    workflow_id: Optional[str] = None
    agent_run_id: Optional[str] = None
    business_entity_id: Optional[str] = None
    business_entity_type: Optional[str] = None

    # LLM call
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    latency_ms: Optional[int] = None

    # Optional timestamp override
    timestamp: Optional[datetime] = None
    extra: Optional[dict] = None


class TokenEventResponse(BaseModel):
    id: str
    total_cost_usd: float
    prompt_cost_usd: float
    completion_cost_usd: float
    total_tokens: int
    timestamp: datetime

    class Config:
        from_attributes = True


class BatchEventRequest(BaseModel):
    events: List[TokenEventRequest]


@router.post("/events", response_model=TokenEventResponse, status_code=201)
async def ingest_event(
    req: TokenEventRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a single token usage event from the SDK."""
    event = TokenEvent(
        id=str(uuid.uuid4()),
        trace_id=req.trace_id,
        span_id=req.span_id,
        team=req.team,
        feature=req.feature,
        workflow_id=req.workflow_id,
        agent_run_id=req.agent_run_id,
        business_entity_id=req.business_entity_id,
        business_entity_type=req.business_entity_type,
        provider=req.provider,
        model=req.model,
        prompt_tokens=req.prompt_tokens,
        completion_tokens=req.completion_tokens,
        total_tokens=req.prompt_tokens + req.completion_tokens,
        latency_ms=req.latency_ms,
        timestamp=req.timestamp or datetime.utcnow(),
        extra=req.extra,
    )

    # Enrich with cost
    event = await process_token_event(event, db)

    db.add(event)
    await db.commit()
    await db.refresh(event)

    return TokenEventResponse(
        id=event.id,
        total_cost_usd=event.total_cost_usd,
        prompt_cost_usd=event.prompt_cost_usd,
        completion_cost_usd=event.completion_cost_usd,
        total_tokens=event.total_tokens,
        timestamp=event.timestamp,
    )


@router.post("/events/batch", status_code=201)
async def ingest_batch(
    req: BatchEventRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ingest multiple token events in one request."""
    results = []
    for event_req in req.events:
        event = TokenEvent(
            id=str(uuid.uuid4()),
            trace_id=event_req.trace_id,
            span_id=event_req.span_id,
            team=event_req.team,
            feature=event_req.feature,
            workflow_id=event_req.workflow_id,
            agent_run_id=event_req.agent_run_id,
            business_entity_id=event_req.business_entity_id,
            business_entity_type=event_req.business_entity_type,
            provider=event_req.provider,
            model=event_req.model,
            prompt_tokens=event_req.prompt_tokens,
            completion_tokens=event_req.completion_tokens,
            total_tokens=event_req.prompt_tokens + event_req.completion_tokens,
            latency_ms=event_req.latency_ms,
            timestamp=event_req.timestamp or datetime.utcnow(),
            extra=event_req.extra,
        )
        event = await process_token_event(event, db)
        db.add(event)
        results.append({"id": event.id, "cost": event.total_cost_usd})

    await db.commit()
    return {"ingested": len(results), "events": results}