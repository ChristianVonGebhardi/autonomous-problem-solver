import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import redis

from app.database import get_db
from app.models import ScanJob, ScanMatch, RemediationSuggestion
from app.schemas import (
    ScanRequest, ScanResult, ScanJobResponse, MatchResult,
    RemediationRequest, RemediationResponse
)
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def get_redis():
    return redis.from_url(settings.redis_url)


def enqueue_scan(scan_job_id: str):
    """Enqueue a scan job using RQ."""
    try:
        from rq import Queue
        r = redis.from_url(settings.redis_url)
        q = Queue('scans', connection=r)
        q.enqueue(
            'app.scanner.process_scan_job',
            scan_job_id,
            settings.database_url,
            job_timeout=120
        )
        logger.info(f"Enqueued scan job: {scan_job_id}")
    except Exception as e:
        logger.error(f"Failed to enqueue job: {e}")
        # Fallback: process synchronously
        _process_sync(scan_job_id)


def _process_sync(scan_job_id: str):
    """Process scan synchronously as fallback."""
    try:
        from app.scanner import process_scan_job
        process_scan_job(scan_job_id, settings.database_url)
    except Exception as e:
        logger.error(f"Sync scan failed: {e}")


@router.post("/scan", response_model=ScanJobResponse, status_code=202)
async def create_scan(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Submit a code snippet for license contamination scanning (async)."""
    scan_id = str(uuid.uuid4())

    # Create scan job record
    scan_job = ScanJob(
        id=scan_id,
        status="pending",
        source=request.source.value,
        language=request.language,
        filename=request.filename,
        code_snippet=request.code,
        metadata_=request.metadata,
    )
    db.add(scan_job)
    db.commit()

    # Enqueue in background
    background_tasks.add_task(enqueue_scan, scan_id)

    return ScanJobResponse(
        scan_id=scan_id,
        status="pending",
        message="Scan job created and queued for processing",
        poll_url=f"/api/v1/scan/{scan_id}"
    )


@router.post("/scan/sync", response_model=ScanResult)
async def create_scan_sync(
    request: ScanRequest,
    db: Session = Depends(get_db)
):
    """Submit a code snippet for synchronous scanning (blocks until complete)."""
    scan_id = str(uuid.uuid4())

    # Create scan job record
    scan_job = ScanJob(
        id=scan_id,
        status="pending",
        source=request.source.value,
        language=request.language,
        filename=request.filename,
        code_snippet=request.code,
        metadata_=request.metadata,
    )
    db.add(scan_job)
    db.commit()

    # Process synchronously
    from app.scanner import process_scan_job
    try:
        process_scan_job(scan_id, settings.database_url)
    except Exception as e:
        logger.error(f"Scan failed: {e}")

    # Refresh and return result
    db.expire(scan_job)
    db.refresh(scan_job)
    return _build_scan_result(scan_job, db)


@router.get("/scan/{scan_id}", response_model=ScanResult)
async def get_scan_result(
    scan_id: str,
    db: Session = Depends(get_db)
):
    """Get the result of a scan job."""
    scan_job = db.query(ScanJob).filter(ScanJob.id == scan_id).first()
    if not scan_job:
        raise HTTPException(status_code=404, detail="Scan job not found")

    return _build_scan_result(scan_job, db)


def _build_scan_result(scan_job: ScanJob, db: Session) -> ScanResult:
    """Build ScanResult from a ScanJob model."""
    from app.license_taxonomy import TIER_RECOMMENDATIONS

    matches = db.query(ScanMatch).filter(
        ScanMatch.scan_job_id == scan_job.id
    ).all()

    match_results = [
        MatchResult(
            match_id=m.id,
            match_type=m.match_type,
            similarity_score=m.similarity_score,
            license_spdx=m.license_spdx,
            license_risk_tier=m.license_risk_tier,
            source_repo=m.source_repo,
            matched_snippet=m.matched_snippet,
        )
        for m in matches
    ]

    risk_tier = scan_job.risk_tier or "unknown"
    if scan_job.status == "completed" and not matches:
        risk_tier = "clean"

    return ScanResult(
        scan_id=scan_job.id,
        status=scan_job.status,
        risk_tier=risk_tier,
        matches=match_results,
        recommendation=TIER_RECOMMENDATIONS.get(risk_tier, ""),
        message=f"Scan {scan_job.status}. Found {len(matches)} potential license matches.",
        created_at=scan_job.created_at,
        completed_at=scan_job.completed_at,
    )


@router.post("/remediate", response_model=RemediationResponse)
async def request_remediation(
    request: RemediationRequest,
    db: Session = Depends(get_db)
):
    """Request a remediation suggestion for a flagged code snippet."""
    scan_job = db.query(ScanJob).filter(ScanJob.id == request.scan_id).first()
    if not scan_job:
        raise HTTPException(status_code=404, detail="Scan job not found")

    if scan_job.status != "completed":
        raise HTTPException(status_code=400, detail="Scan must be completed first")

    # Get the highest-risk match
    if request.match_id:
        match = db.query(ScanMatch).filter(
            ScanMatch.id == request.match_id,
            ScanMatch.scan_job_id == request.scan_id
        ).first()
    else:
        match = db.query(ScanMatch).filter(
            ScanMatch.scan_job_id == request.scan_id
        ).order_by(ScanMatch.similarity_score.desc()).first()

    license_spdx = match.license_spdx if match else "Unknown"
    risk_tier = match.license_risk_tier if match else "unknown"

    # Get remediation suggestion
    from app.remediation import get_remediation_suggestion
    suggestion = get_remediation_suggestion(
        original_code=scan_job.code_snippet,
        license_spdx=license_spdx,
        risk_tier=risk_tier,
        api_key=settings.openai_api_key or None
    )

    # Save remediation
    remediation_id = str(uuid.uuid4())
    remediation = RemediationSuggestion(
        id=remediation_id,
        scan_job_id=scan_job.id,
        match_id=match.id if match else None,
        original_code=scan_job.code_snippet,
        suggested_code=suggestion.get("suggested_code"),
        explanation=suggestion.get("explanation"),
        status=suggestion.get("status", "completed"),
    )
    db.add(remediation)
    db.commit()

    return RemediationResponse(
        remediation_id=remediation_id,
        scan_id=request.scan_id,
        original_code=scan_job.code_snippet,
        suggested_code=suggestion.get("suggested_code"),
        explanation=suggestion.get("explanation"),
        status=suggestion.get("status", "completed"),
    )


@router.get("/scans", response_model=list)
async def list_scans(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    risk_tier: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List scan jobs with optional filtering."""
    query = db.query(ScanJob)

    if status:
        query = query.filter(ScanJob.status == status)
    if risk_tier:
        query = query.filter(ScanJob.risk_tier == risk_tier)

    scan_jobs = query.order_by(ScanJob.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for job in scan_jobs:
        match_count = db.query(ScanMatch).filter(
            ScanMatch.scan_job_id == job.id
        ).count()
        results.append({
            "scan_id": job.id,
            "status": job.status,
            "source": job.source,
            "language": job.language,
            "filename": job.filename,
            "risk_tier": job.risk_tier,
            "match_count": match_count,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        })

    return results