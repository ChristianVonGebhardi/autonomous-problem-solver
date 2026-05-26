from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class RiskTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"
    CLEAN = "clean"


class ScanSource(str, Enum):
    AI_ASSISTANT = "ai_assistant"
    PRE_COMMIT = "pre_commit"
    CI_CD = "ci_cd"
    API = "api"


class ScanRequest(BaseModel):
    code: str = Field(..., description="Code snippet to scan", min_length=1)
    language: Optional[str] = Field(None, description="Programming language")
    source: ScanSource = Field(ScanSource.API, description="Where the code originated")
    filename: Optional[str] = Field(None, description="Source filename")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class MatchResult(BaseModel):
    match_id: str
    match_type: str  # exact, near_duplicate, semantic
    similarity_score: float
    license_spdx: str
    license_risk_tier: str
    source_repo: Optional[str]
    matched_snippet: Optional[str]


class ScanResult(BaseModel):
    scan_id: str
    status: str
    risk_tier: Optional[str]
    matches: List[MatchResult] = []
    recommendation: str = ""
    message: str = ""
    created_at: datetime
    completed_at: Optional[datetime] = None


class ScanJobResponse(BaseModel):
    scan_id: str
    status: str
    message: str
    poll_url: str


class RemediationRequest(BaseModel):
    scan_id: str
    match_id: Optional[str] = None


class RemediationResponse(BaseModel):
    remediation_id: str
    scan_id: str
    original_code: str
    suggested_code: Optional[str]
    explanation: Optional[str]
    status: str


class CorpusSnippetCreate(BaseModel):
    source_repo: str
    source_file: str
    license_spdx: str
    language: Optional[str]
    code_snippet: str


class DashboardStats(BaseModel):
    total_scans: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    clean_count: int
    top_licenses: List[Dict[str, Any]]
    recent_scans: List[Dict[str, Any]]
    risk_trend: List[Dict[str, Any]]


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: str
    corpus_size: int