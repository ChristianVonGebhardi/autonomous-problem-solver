"""
SQLAlchemy ORM models.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, JSON, Text,
    ForeignKey, Index, func
)
from sqlalchemy.orm import relationship
from .database import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    expected_steps = Column(JSON, nullable=True)
    expected_tools = Column(JSON, nullable=True)
    baseline_count = Column(Integer, default=0)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    traces = relationship("TraceRun", back_populates="workflow", lazy="select")


class TraceRun(Base):
    __tablename__ = "trace_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(255), unique=True, nullable=False, index=True)
    workflow_id = Column(String(255), ForeignKey("workflows.workflow_id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    span_count = Column(Integer, default=0)
    is_baseline = Column(Boolean, default=False)
    avg_confidence = Column(Float, nullable=True)
    tool_sequence = Column(JSON, nullable=True)
    step_sequence = Column(JSON, nullable=True)
    run_embedding = Column(JSON, nullable=True)  # Stored as float list
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="traces")
    spans = relationship("SpanRecord", back_populates="trace_run", lazy="select")
    drift_score = relationship("DriftScore", back_populates="trace_run", uselist=False)

    __table_args__ = (
        Index("ix_trace_workflow_time", "workflow_id", "start_time"),
    )


class SpanRecord(Base):
    __tablename__ = "spans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    span_id = Column(String(255), unique=True, nullable=False, index=True)
    run_id = Column(String(255), ForeignKey("trace_runs.run_id"), nullable=False)
    workflow_id = Column(String(255), nullable=False, index=True)
    step_name = Column(String(255), nullable=False)
    step_index = Column(Integer, default=0)
    tool_name = Column(String(255), nullable=True)
    tool_input = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)
    output = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    retrieved_chunk_hashes = Column(JSON, nullable=True)
    token_count = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    start_time = Column(DateTime, nullable=True)
    reasoning_embedding = Column(JSON, nullable=True)
    attributes = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    trace_run = relationship("TraceRun", back_populates="spans")


class DriftScore(Base):
    __tablename__ = "drift_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String(255), nullable=False, index=True)
    run_id = Column(String(255), ForeignKey("trace_runs.run_id"), nullable=False, unique=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    structural_score = Column(Float, nullable=False, default=0.0)
    semantic_score = Column(Float, nullable=False, default=0.0)
    distributional_score = Column(Float, nullable=False, default=0.0)
    composite_score = Column(Float, nullable=False, default=0.0)
    alert_level = Column(String(50), default="normal")  # normal | warning | alert
    details = Column(JSON, nullable=True)

    trace_run = relationship("TraceRun", back_populates="drift_score")

    __table_args__ = (
        Index("ix_drift_workflow_time", "workflow_id", "timestamp"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String(255), nullable=False, index=True)
    run_id = Column(String(255), nullable=False)
    alert_level = Column(String(50), nullable=False)
    composite_score = Column(Float, nullable=False)
    structural_score = Column(Float, nullable=False)
    semantic_score = Column(Float, nullable=False)
    distributional_score = Column(Float, nullable=False)
    explanation = Column(Text, nullable=True)
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)