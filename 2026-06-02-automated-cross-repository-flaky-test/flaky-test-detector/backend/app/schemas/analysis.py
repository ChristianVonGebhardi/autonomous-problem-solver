from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class FlakinessCause(str, Enum):
    timing = "timing"
    concurrency = "concurrency"
    environment = "environment"
    state_leakage = "state_leakage"
    unknown = "unknown"


class FixStatus(str, Enum):
    pending = "pending"
    synthesizing = "synthesizing"
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"
    applied = "applied"


class CauseScore(BaseModel):
    cause: FlakinessCause
    confidence: float
    evidence: List[str] = []


class RootCauseResult(BaseModel):
    primary_cause: FlakinessCause
    confidence: float
    secondary_causes: List[CauseScore] = []
    evidence: Dict[str, Any] = {}
    classifier_version: str = "rule_based_v1"


class FlakyTestOut(BaseModel):
    id: int
    repo: str
    test_name: str
    test_file: Optional[str]
    flakiness_score: float
    total_runs: int
    failed_runs: int
    pass_rate: Optional[float]
    is_active: bool
    first_detected_at: datetime
    last_seen_at: Optional[datetime]
    primary_cause: Optional[str] = None
    cause_confidence: Optional[float] = None
    fix_count: int = 0

    class Config:
        from_attributes = True


class AnalysisOut(BaseModel):
    id: int
    flaky_test_id: int
    primary_cause: str
    confidence: float
    secondary_causes: Optional[List[Dict]] = None
    evidence: Optional[Dict] = None
    classifier_version: str
    created_at: datetime

    class Config:
        from_attributes = True


class FixProposalOut(BaseModel):
    id: int
    flaky_test_id: int
    status: str
    root_cause: Optional[str]
    patch_diff: Optional[str]
    explanation: Optional[str]
    affected_files: Optional[List[str]]
    confidence: Optional[float]
    pr_url: Optional[str]
    pr_number: Optional[int]
    feedback_accepted: Optional[bool]
    llm_model: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackIn(BaseModel):
    accepted: bool
    note: Optional[str] = None


class DashboardStats(BaseModel):
    total_repos: int
    total_test_runs: int
    total_flaky_tests: int
    active_flaky_tests: int
    fixes_proposed: int
    fixes_accepted: int
    fixes_rejected: int
    acceptance_rate: float
    cause_breakdown: Dict[str, int]
    top_flaky_tests: List[Dict]