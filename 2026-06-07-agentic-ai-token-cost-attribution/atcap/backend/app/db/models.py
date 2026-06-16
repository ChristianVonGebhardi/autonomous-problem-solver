from sqlalchemy import (
    Column, String, Float, Integer, DateTime, JSON, Boolean,
    ForeignKey, Text, Index
)
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.db.base import Base


def gen_uuid():
    return str(uuid.uuid4())


class TokenEvent(Base):
    """Raw token usage event from SDK instrumentation."""
    __tablename__ = "token_events"

    id = Column(String, primary_key=True, default=gen_uuid)
    trace_id = Column(String, nullable=True, index=True)
    span_id = Column(String, nullable=True)

    # Attribution context
    team = Column(String, nullable=False, index=True)
    feature = Column(String, nullable=False, index=True)
    workflow_id = Column(String, nullable=True, index=True)
    agent_run_id = Column(String, nullable=True)
    business_entity_id = Column(String, nullable=True)  # ticket ID, PR number, etc.
    business_entity_type = Column(String, nullable=True)  # "ticket", "pr", "pipeline"

    # LLM call details
    provider = Column(String, nullable=False)  # openai, anthropic, bedrock, vertex
    model = Column(String, nullable=False, index=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    # Cost (computed by backend)
    prompt_cost_usd = Column(Float, default=0.0)
    completion_cost_usd = Column(Float, default=0.0)
    total_cost_usd = Column(Float, default=0.0)

    # Timing
    latency_ms = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Extra metadata
    extra = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_token_events_team_timestamp", "team", "timestamp"),
        Index("ix_token_events_feature_timestamp", "feature", "timestamp"),
    )


class CostAggregate(Base):
    """Pre-computed cost aggregates for fast dashboard queries."""
    __tablename__ = "cost_aggregates"

    id = Column(String, primary_key=True, default=gen_uuid)
    window_start = Column(DateTime, nullable=False, index=True)
    window_end = Column(DateTime, nullable=False)
    window_size_seconds = Column(Integer, default=900)  # 15 min default

    # Dimension
    dimension_type = Column(String, nullable=False)  # "team", "feature", "model", "workflow"
    dimension_value = Column(String, nullable=False)

    # Metrics
    total_cost_usd = Column(Float, default=0.0)
    total_tokens = Column(Integer, default=0)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    call_count = Column(Integer, default=0)
    avg_latency_ms = Column(Float, nullable=True)

    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_cost_agg_dim_window", "dimension_type", "dimension_value", "window_start"),
    )


class BudgetPolicy(Base):
    """Budget thresholds and alert policies."""
    __tablename__ = "budget_policies"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Scope
    dimension_type = Column(String, nullable=False)  # "team", "feature", "model", "global"
    dimension_value = Column(String, nullable=True)  # null = global

    # Budget
    budget_usd = Column(Float, nullable=False)
    period = Column(String, default="monthly")  # daily, weekly, monthly

    # Alert thresholds (% of budget)
    warn_threshold_pct = Column(Float, default=80.0)
    critical_threshold_pct = Column(Float, default=95.0)

    # State
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    alerts = relationship("BudgetAlert", back_populates="policy")


class BudgetAlert(Base):
    """Triggered budget alerts."""
    __tablename__ = "budget_alerts"

    id = Column(String, primary_key=True, default=gen_uuid)
    policy_id = Column(String, ForeignKey("budget_policies.id"), nullable=False)

    alert_level = Column(String, nullable=False)  # "warn", "critical"
    current_spend_usd = Column(Float, nullable=False)
    budget_usd = Column(Float, nullable=False)
    spend_pct = Column(Float, nullable=False)

    message = Column(Text, nullable=True)
    notified_slack = Column(Boolean, default=False)
    acknowledged = Column(Boolean, default=False)

    triggered_at = Column(DateTime, default=datetime.utcnow, index=True)

    policy = relationship("BudgetPolicy", back_populates="alerts")


class ValueEvent(Base):
    """Business value signals (PRs merged, tickets resolved, revenue)."""
    __tablename__ = "value_events"

    id = Column(String, primary_key=True, default=gen_uuid)
    source = Column(String, nullable=False)  # "github", "jira", "linear", "webhook"
    event_type = Column(String, nullable=False)  # "pr_merged", "ticket_closed", "deploy", "revenue"

    # Attribution
    team = Column(String, nullable=True, index=True)
    feature = Column(String, nullable=True)
    business_entity_id = Column(String, nullable=True, index=True)

    # Value
    value_points = Column(Float, default=1.0)  # normalized value score
    value_usd = Column(Float, nullable=True)    # explicit USD value if available
    title = Column(String, nullable=True)
    url = Column(String, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    extra = Column(JSON, nullable=True)


class ROIRecord(Base):
    """Correlated cost vs value records for ROI analysis."""
    __tablename__ = "roi_records"

    id = Column(String, primary_key=True, default=gen_uuid)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Dimension
    team = Column(String, nullable=True, index=True)
    feature = Column(String, nullable=True)

    # Cost side
    total_cost_usd = Column(Float, default=0.0)
    total_tokens = Column(Integer, default=0)
    call_count = Column(Integer, default=0)

    # Value side
    value_events_count = Column(Integer, default=0)
    value_points = Column(Float, default=0.0)
    value_usd = Column(Float, nullable=True)

    # ROI
    cost_per_value_point = Column(Float, nullable=True)
    roi_ratio = Column(Float, nullable=True)  # value_usd / cost_usd

    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_roi_team_period", "team", "period_start"),
    )


class PricingCatalog(Base):
    """Versioned LLM pricing catalog."""
    __tablename__ = "pricing_catalog"

    id = Column(String, primary_key=True, default=gen_uuid)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False, index=True)

    prompt_cost_per_1k_tokens = Column(Float, nullable=False)
    completion_cost_per_1k_tokens = Column(Float, nullable=False)

    effective_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    effective_to = Column(DateTime, nullable=True)
    is_current = Column(Boolean, default=True)
    source_url = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_pricing_model_current", "model", "is_current"),
    )