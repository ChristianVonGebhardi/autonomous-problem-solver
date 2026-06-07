"""SQLAlchemy ORM models for the drift detection platform."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer,
    String, Text, JSON, Index, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from api.database import Base


def _uuid():
    return str(uuid.uuid4())


class Workflow(Base):
    """Registered agentic workflow definition."""
    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    expected_tools = Column(JSON, nullable=True)  # list of expected tool names
    created_at = Column(DateTime, server_default=text("NOW()"), nullable=False)
    updated_at = Column(DateTime, server_default=text("NOW()"), onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    traces = relationship("AgentTrace", back_populates="workflow", lazy="dynamic")
    baselines = relationship("BaselineRun", back_populates="workflow", lazy="dynamic")
    drift_scores = relationship("DriftScore", back_populates="workflow", lazy="dynamic")


class AgentTrace(Base):
    """Raw agent run trace ingested from the SDK."""
    __tablename__ = "agent_traces"

    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(36), nullable=False, unique=True, index=True)
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False, index=True)
    start_time = Column(Float, nullable=False)  # Unix timestamp
    end_time = Column(Float, nullable=True)
    duration_ms = Column(Float, nullable=True)
    step_count = Column(Integer, nullable=True)
    tool_sequence = Column(JSON, nullable=True)  # ["search", "summarize", ...]
    steps = Column(JSON, nullable=True)           # Full step data
    metadata = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    ingested_at = Column(DateTime, server_default=text("NOW()"))
    processed = Column(Boolean, default=False, index=True)

    workflow = relationship("Workflow", back_populates="traces")
    drift_score = relationship("DriftScore", back_populates="trace", uselist=False)

    __table_args__ = (
        Index("ix_traces_workflow_processed", "workflow_id", "processed"),
        Index("ix_traces_start_time", "start_time"),
    )


class BaselineRun(Base):
    """
    Human-approved 'golden run' traces that establish the behavioral baseline.
    
    Embeddings are stored as JSON arrays (PostgreSQL) — in production, Qdrant
    would hold these for ANN search; here we use the DB for MVP simplicity.
    """
    __tablename__ = "baseline_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False, index=True)
    run_id = Column(String(36), nullable=False)
    tool_sequence = Column(JSON, nullable=False)
    step_embeddings = Column(JSON, nullable=True)   # list of embedding vectors
    run_embedding = Column(JSON, nullable=True)     # aggregate run-level embedding
    confidence_stats = Column(JSON, nullable=True)  # mean, std of confidence scores
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(DateTime, server_default=text("NOW()"))
    notes = Column(Text, nullable=True)

    workflow = relationship("Workflow", back_populates="baselines")

    __table_args__ = (
        Index("ix_baselines_workflow", "workflow_id"),
    )


class DriftScore(Base):
    """
    Unified drift score computed for each processed agent trace.
    TimescaleDB hypertable on ingested_at enables efficient time-series queries.
    """
    __tablename__ = "drift_scores"

    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(36), ForeignKey("agent_traces.run_id"), nullable=False, index=True)
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False, index=True)
    ingested_at = Column(DateTime, server_default=text("NOW()"), index=True)

    # Three-layer scores (0.0–1.0, higher = more drift)
    structural_score = Column(Float, nullable=True)
    semantic_score = Column(Float, nullable=True)
    distributional_score = Column(Float, nullable=True)

    # Composite
    composite_score = Column(Float, nullable=True)
    alert_triggered = Column(Boolean, default=False)
    severity = Column(String(20), nullable=True)  # low, medium, high, critical

    # Detailed breakdown
    structural_detail = Column(JSON, nullable=True)
    semantic_detail = Column(JSON, nullable=True)
    distributional_detail = Column(JSON, nullable=True)

    # LLM explanation (only populated on alert)
    explanation = Column(Text, nullable=True)

    trace = relationship("AgentTrace", back_populates="drift_score")
    workflow = relationship("Workflow", back_populates="drift_scores")

    __table_args__ = (
        Index("ix_drift_workflow_time", "workflow_id", "ingested_at"),
    )


class CusumState(Base):
    """
    Persisted CUSUM algorithm state per workflow.
    Allows the worker to resume correctly after restarts.
    """
    __tablename__ = "cusum_states"

    id = Column(String(36), primary_key=True, default=_uuid)
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False, unique=True)
    cusum_pos = Column(Float, default=0.0)  # Positive CUSUM accumulator
    cusum_neg = Column(Float, default=0.0)  # Negative CUSUM accumulator
    ewma_value = Column(Float, nullable=True)
    baseline_mean = Column(Float, nullable=True)
    baseline_std = Column(Float, nullable=True)
    sample_count = Column(Integer, default=0)
    updated_at = Column(DateTime, server_default=text("NOW()"), onupdate=datetime.utcnow)