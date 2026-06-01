import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, Text,
    ForeignKey, DateTime, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text)
    system_prompt_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    inference_logs = relationship("InferenceLog", back_populates="template")
    golden_references = relationship("GoldenReference", back_populates="template")
    quality_scores = relationship("QualityScore", back_populates="template")
    drift_alerts = relationship("DriftAlert", back_populates="template")


class GoldenReference(Base):
    __tablename__ = "golden_references"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("prompt_templates.id", ondelete="CASCADE"))
    input_messages = Column(JSONB, nullable=False)
    expected_output = Column(Text, nullable=False)
    output_embedding = Column(Vector(1536))
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    template = relationship("PromptTemplate", back_populates="golden_references")


class InferenceLog(Base):
    __tablename__ = "inference_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("prompt_templates.id"))
    template_name = Column(String(255))
    request_payload = Column(JSONB, nullable=False)
    response_payload = Column(JSONB)
    model = Column(String(255))
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    latency_ms = Column(Float)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    template = relationship("PromptTemplate", back_populates="inference_logs")
    quality_scores = relationship("QualityScore", back_populates="inference_log")


class QualityScore(Base):
    __tablename__ = "quality_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inference_log_id = Column(UUID(as_uuid=True), ForeignKey("inference_logs.id", ondelete="CASCADE"))
    template_id = Column(UUID(as_uuid=True), ForeignKey("prompt_templates.id"))
    metric_name = Column(String(100), nullable=False)
    score = Column(Float, nullable=False)
    metadata_ = Column("metadata", JSONB, default=dict)
    scored_at = Column(DateTime(timezone=True), default=utcnow)

    inference_log = relationship("InferenceLog", back_populates="quality_scores")
    template = relationship("PromptTemplate", back_populates="quality_scores")


class DriftAlert(Base):
    __tablename__ = "drift_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("prompt_templates.id"))
    template_name = Column(String(255))
    metric_name = Column(String(100), nullable=False)
    detector_type = Column(String(50), nullable=False)
    severity = Column(String(50), default="warning")
    baseline_mean = Column(Float)
    current_mean = Column(Float)
    p_value = Column(Float)
    cusum_stat = Column(Float)
    evidence = Column(JSONB, default=dict)
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    template = relationship("PromptTemplate", back_populates="drift_alerts")


class MetricAggregate(Base):
    __tablename__ = "metric_aggregates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("prompt_templates.id"))
    metric_name = Column(String(100), nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    sample_count = Column(Integer, nullable=False)
    mean_score = Column(Float, nullable=False)
    std_score = Column(Float)
    min_score = Column(Float)
    max_score = Column(Float)
    p10_score = Column(Float)
    p50_score = Column(Float)
    p90_score = Column(Float)
    created_at = Column(DateTime(timezone=True), default=utcnow)