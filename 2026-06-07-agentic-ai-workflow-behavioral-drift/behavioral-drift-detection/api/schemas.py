"""Pydantic schemas for API request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Traces ────────────────────────────────────────────────────────────────────

class StepData(BaseModel):
    span_id: str
    run_id: str
    workflow_id: str
    step_index: int
    tool_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    output_text: Optional[str] = None
    confidence: Optional[float] = None
    retrieved_chunks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class TraceIngest(BaseModel):
    """Payload emitted by the BehaviorTrace SDK on run completion."""
    run_id: str
    workflow_id: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    steps: list[StepData] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    tool_sequence: list[str] = Field(default_factory=list)
    step_count: int = 0


class TraceResponse(BaseModel):
    run_id: str
    workflow_id: str
    ingested_at: datetime
    processed: bool
    drift_score: Optional["DriftScoreResponse"] = None

    model_config = {"from_attributes": True}


# ── Workflows ─────────────────────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    expected_tools: Optional[list[str]] = None


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    expected_tools: Optional[list[str]] = None
    is_active: Optional[bool] = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    expected_tools: Optional[list[str]]
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


# ── Baselines ─────────────────────────────────────────────────────────────────

class BaselineCreate(BaseModel):
    """Approve a trace as a golden run baseline."""
    run_id: str
    approved_by: Optional[str] = None
    notes: Optional[str] = None


class BaselineResponse(BaseModel):
    id: str
    workflow_id: str
    run_id: str
    tool_sequence: list[str]
    approved_by: Optional[str]
    approved_at: datetime
    notes: Optional[str]

    model_config = {"from_attributes": True}


# ── Drift Scores ──────────────────────────────────────────────────────────────

class DriftScoreResponse(BaseModel):
    id: str
    run_id: str
    workflow_id: str
    ingested_at: datetime
    structural_score: Optional[float]
    semantic_score: Optional[float]
    distributional_score: Optional[float]
    composite_score: Optional[float]
    alert_triggered: bool
    severity: Optional[str]
    structural_detail: Optional[dict]
    semantic_detail: Optional[dict]
    distributional_detail: Optional[dict]
    explanation: Optional[str]

    model_config = {"from_attributes": True}


class DriftTimeSeriesPoint(BaseModel):
    timestamp: datetime
    run_id: str
    composite_score: float
    structural_score: Optional[float]
    semantic_score: Optional[float]
    distributional_score: Optional[float]
    severity: Optional[str]
    alert_triggered: bool


class WorkflowDriftSummary(BaseModel):
    workflow_id: str
    workflow_name: str
    recent_composite_score: Optional[float]
    trend: str  # "stable", "increasing", "decreasing"
    alert_count_24h: int
    baseline_count: int
    trace_count_24h: int
    last_alert_at: Optional[datetime]