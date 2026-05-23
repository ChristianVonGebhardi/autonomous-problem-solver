#!/usr/bin/env python3
"""
PR Analysis Engine - FastAPI service for ML-based complexity scoring
"""
import os
import math
import logging
from typing import List, Optional
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

logging.basicConfig(level=logging.INFO, format="[analysis] %(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="PR Analysis Engine", version="1.0.0")

# Service configuration
ANALYSIS_PORT = int(os.getenv("ANALYSIS_SERVICE_PORT", "8081"))
ROUTING_SERVICE_URL = os.getenv("ROUTING_SERVICE_URL", "http://localhost:8082")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "reviewer")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "reviewer_pass")
POSTGRES_DB = os.getenv("POSTGRES_DB", "code_review_coordinator")


class AnalysisRequest(BaseModel):
    pr_id: int
    lines_added: int = 0
    lines_deleted: int = 0
    files_changed: int = 0
    files: List[str] = []
    author: str = ""


class AnalysisResponse(BaseModel):
    pr_id: int
    complexity_score: float
    estimated_minutes: int
    risk_level: str
    breakdown: dict


# File type weights for complexity calculation
FILE_TYPE_WEIGHTS = {
    ".go": 1.2,
    ".py": 1.1,
    ".js": 1.0,
    ".ts": 1.1,
    ".tsx": 1.1,
    ".jsx": 1.0,
    ".java": 1.2,
    ".rs": 1.4,
    ".cpp": 1.5,
    ".c": 1.3,
    ".h": 1.0,
    ".sql": 1.3,
    ".tf": 1.4,  # Terraform
    ".yaml": 0.7,
    ".yml": 0.7,
    ".json": 0.5,
    ".md": 0.2,
    ".txt": 0.1,
    ".css": 0.4,
    ".scss": 0.5,
    ".html": 0.6,
    ".sh": 1.1,
    ".proto": 1.2,
    "Dockerfile": 0.8,
    "Makefile": 0.7,
}

HIGH_RISK_PATTERNS = [
    "auth", "security", "payment", "billing", "crypto", "password",
    "token", "secret", "key", "cert", "ssl", "tls", "permission",
    "migration", "schema", "database", "db", "transaction",
    "config", "env", "deploy", "infrastructure", "k8s", "kubernetes"
]


def get_file_extension(filename: str) -> str:
    """Get file extension or special filename."""
    base = os.path.basename(filename)
    if base in FILE_TYPE_WEIGHTS:
        return base
    _, ext = os.path.splitext(base)
    return ext.lower() if ext else ".txt"


def compute_complexity_score(
    lines_added: int,
    lines_deleted: int,
    files_changed: int,
    files: List[str]
) -> tuple[float, dict]:
    """
    Compute PR complexity score (0.0 - 1.0) using heuristic ML model.
    
    Factors:
    - Total lines changed (log-scaled)
    - Number of files changed
    - File type complexity weights
    - High-risk file patterns
    - Churn ratio (deletions vs additions)
    """
    breakdown = {}
    
    total_lines = lines_added + lines_deleted
    
    # 1. Size score (0-0.35): log-scale lines changed
    # 0 lines = 0, 50 lines = ~0.15, 200 lines = ~0.25, 1000+ lines = ~0.35
    if total_lines == 0:
        size_score = 0.0
    else:
        size_score = min(0.35, math.log(total_lines + 1) / math.log(2000) * 0.35)
    breakdown["size_score"] = round(size_score, 3)
    
    # 2. Breadth score (0-0.20): files changed
    # 1 file = 0.05, 5 files = 0.12, 10 files = 0.18, 20+ files = 0.20
    breadth_score = min(0.20, math.log(files_changed + 1) / math.log(25) * 0.20)
    breakdown["breadth_score"] = round(breadth_score, 3)
    
    # 3. File type score (0-0.25): weighted by file complexity
    type_score = 0.0
    if files:
        weights = []
        for f in files:
            ext = get_file_extension(f)
            weight = FILE_TYPE_WEIGHTS.get(ext, 0.8)
            weights.append(weight)
        avg_weight = sum(weights) / len(weights)
        # Normalize: max weight ~1.5, min ~0.1
        type_score = min(0.25, (avg_weight - 0.1) / 1.4 * 0.25)
    breakdown["type_score"] = round(type_score, 3)
    
    # 4. Risk score (0-0.20): sensitive file patterns
    risk_score = 0.0
    if files:
        risk_files = 0
        for f in files:
            f_lower = f.lower()
            for pattern in HIGH_RISK_PATTERNS:
                if pattern in f_lower:
                    risk_files += 1
                    break
        risk_ratio = risk_files / len(files)
        risk_score = min(0.20, risk_ratio * 0.20)
    breakdown["risk_score"] = round(risk_score, 3)
    
    # 5. Churn ratio score (0-0.10): heavy deletions suggest refactoring
    churn_score = 0.0
    if total_lines > 0:
        deletion_ratio = lines_deleted / total_lines
        # High deletion ratio = complex refactoring
        churn_score = min(0.10, deletion_ratio * 0.10)
    breakdown["churn_score"] = round(churn_score, 3)
    
    total_score = size_score + breadth_score + type_score + risk_score + churn_score
    total_score = min(1.0, max(0.0, total_score))
    breakdown["total"] = round(total_score, 3)
    
    return total_score, breakdown


def estimate_review_minutes(complexity_score: float, lines_added: int, files_changed: int) -> int:
    """
    Estimate review time in minutes based on complexity.
    
    Based on research: median review time ~15min for small PRs, 
    up to 2+ hours for large complex ones.
    """
    # Base time: 10-15 minutes minimum
    base_minutes = 10
    
    # Lines-based estimate: ~2 minutes per 10 lines for simple, ~5 min for complex
    lines_factor = (lines_added / 10) * (2 + complexity_score * 3)
    
    # Files overhead: context switching cost
    files_factor = files_changed * 3
    
    # Complexity multiplier
    complexity_multiplier = 1.0 + complexity_score * 2.0
    
    total = (base_minutes + lines_factor + files_factor) * complexity_multiplier
    
    # Cap at 480 minutes (8 hours) and floor at 10 minutes
    return max(10, min(480, int(total)))


def get_risk_level(complexity_score: float, risk_score: float) -> str:
    """Determine risk level from complexity and risk scores."""
    if risk_score >= 0.15 or complexity_score >= 0.75:
        return "high"
    elif risk_score >= 0.08 or complexity_score >= 0.45:
        return "medium"
    else:
        return "low"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "analysis"}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_pr(req: AnalysisRequest):
    """Analyze a PR and compute complexity score."""
    logger.info(f"Analyzing PR {req.pr_id}: {req.lines_added}+/{req.lines_deleted}- lines, {req.files_changed} files")
    
    complexity_score, breakdown = compute_complexity_score(
        req.lines_added,
        req.lines_deleted,
        req.files_changed,
        req.files
    )
    
    estimated_minutes = estimate_review_minutes(
        complexity_score,
        req.lines_added,
        req.files_changed
    )
    
    risk_level = get_risk_level(complexity_score, breakdown.get("risk_score", 0))
    
    logger.info(
        f"PR {req.pr_id}: complexity={complexity_score:.3f}, "
        f"estimated={estimated_minutes}min, risk={risk_level}"
    )
    
    # Update PR in database via routing service or direct DB
    await update_pr_analysis(req.pr_id, complexity_score, estimated_minutes)
    
    # Trigger routing for this PR
    await trigger_routing(req.pr_id)
    
    return AnalysisResponse(
        pr_id=req.pr_id,
        complexity_score=round(complexity_score, 4),
        estimated_minutes=estimated_minutes,
        risk_level=risk_level,
        breakdown=breakdown
    )


@app.post("/analyze/batch")
async def analyze_batch(requests: List[AnalysisRequest]):
    """Analyze multiple PRs."""
    results = []
    for req in requests:
        result = await analyze_pr(req)
        results.append(result)
    return results


async def update_pr_analysis(pr_id: int, complexity_score: float, estimated_minutes: int):
    """Update PR analysis results via webhook service API."""
    try:
        webhook_url = os.getenv("WEBHOOK_SERVICE_URL", "http://localhost:8080")
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.patch(
                f"{webhook_url}/api/prs/{pr_id}/analysis",
                json={
                    "complexity_score": complexity_score,
                    "estimated_minutes": estimated_minutes
                }
            )
    except Exception as e:
        logger.warning(f"Could not update PR analysis in DB: {e}")


async def trigger_routing(pr_id: int):
    """Trigger routing for analyzed PR."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{ROUTING_SERVICE_URL}/route/{pr_id}",
                json={}
            )
        logger.info(f"Triggered routing for PR {pr_id}")
    except Exception as e:
        logger.warning(f"Could not trigger routing for PR {pr_id}: {e}")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=ANALYSIS_PORT,
        reload=False,
        log_level="info"
    )