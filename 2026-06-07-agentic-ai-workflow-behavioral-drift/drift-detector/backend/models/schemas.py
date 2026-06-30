"""
Pydantic schemas for API request/response models and internal data structures.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
import uuid


# ── Workflow ──────────────────────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    workflow_id: str = Field(..., description="Unique identifier for the workflow")
    name: str
    description: Optional[str] = None
    expected_steps: Optional[List[str]] = None
    expected_tools: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: str
    name: str
    description: Optional[str] = None
    expected_steps: Optional[List[str]] = None
    expected_tools: Optional[List[str]] = None
    baseline_count: int = 0
    created_at: datetime
    updated_at: datetime


# ── Spans ─────────────────────────────────────────────────────────────────────

class SpanData(BaseModel):
    span_id: str
    trace_id: str
    workflow_id: str
    step_name: str
    step_index: int
    tool_name: Optional[str] = None
    tool_input: Optional[str] = None
    reasoning: Optional[str] = None
    output: Optional[str] = None
    confidence: Optional[float] = None
    retrieved_chunk_hashes: List[str] = []
    token_count: Optional[int] = None
    latency_ms: Optional[float] = None
    start_time: float
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = {}
    reasoning_embedding: Optional[List[float]] = None


# ── Trace Run ─────────────────────────────────────────────────────────────────

class TraceIngestion(BaseModel):
    """Incoming trace run from the SDK."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    start_time: float
    end_time: Optional[float] = None
    span_count: int = 0
    spans: List[SpanData] = []
    metadata: Dict[str, Any] = {}
    tool_sequence: List[Optional[str]] = []
    step_sequence: List[str] = []
    avg_confidence: float = 0.0


class TraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    workflow_id: str
    start_time: datetime
    span_count: int
    is_baseline: bool
    avg_confidence: Optional[float] = None
    tool_sequence: Optional[List[str]] = None
    step_sequence: Optional[List[str]] = None
    created_at: datetime


# ── Drift Scores ──────────────────────────────────────────────────────────────

class DriftScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: str
    run_id: str
    timestamp: datetime
    structural_score: float
    semantic_score: float
    distributional_score: float
    composite_score: float
    alert_level: str  # "normal" | "warning" | "alert"
    details: Optional[Dict[str, Any]] = None


class DriftTimelineResponse(BaseModel):
    workflow_id: str
    scores: List[DriftScoreResponse]
    baseline_count: int
    latest_composite: Optional[float] = None
    alert_level: Optional[str] = None


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: str
    run_id: str
    alert_level: str
    composite_score: float
    structural_score: float
    semantic_score: float
    distributional_score: float
    explanation: Optional[str] = None
    acknowledged: bool
    created_at: datetime


# ── Baseline ──────────────────────────────────────────────────────────────────

class BaselinePromoteRequest(BaseModel):
    run_id: str
    notes: Optional[str] = None


class BaselineResponse(BaseModel):
    success: bool
    message: str
    workflow_id: str
    run_id: str
    baseline_count: int