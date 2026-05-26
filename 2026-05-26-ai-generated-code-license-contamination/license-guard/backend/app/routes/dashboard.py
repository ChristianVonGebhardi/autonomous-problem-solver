import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models import ScanJob, ScanMatch, CorpusSnippet
from app.schemas import DashboardStats

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics for compliance overview."""
    
    # Total scans
    total_scans = db.query(func.count(ScanJob.id)).filter(
        ScanJob.status == "completed"
    ).scalar() or 0
    
    # Risk tier counts
    tier_counts = db.query(
        ScanJob.risk_tier,
        func.count(ScanJob.id)
    ).filter(
        ScanJob.status == "completed"
    ).group_by(ScanJob.risk_tier).all()
    
    tier_map = {t: c for t, c in tier_counts}
    
    # Top licenses found
    top_licenses = db.query(
        ScanMatch.license_spdx,
        ScanMatch.license_risk_tier,
        func.count(ScanMatch.id).label('count')
    ).group_by(
        ScanMatch.license_spdx,
        ScanMatch.license_risk_tier
    ).order_by(desc('count')).limit(10).all()
    
    # Recent scans
    recent_jobs = db.query(ScanJob).filter(
        ScanJob.status == "completed"
    ).order_by(desc(ScanJob.created_at)).limit(10).all()
    
    recent_scans = [
        {
            "scan_id": job.id,
            "filename": job.filename or "unknown",
            "language": job.language or "unknown",
            "risk_tier": job.risk_tier or "clean",
            "source": job.source,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "match_count": len(job.matches),
        }
        for job in recent_jobs
    ]
    
    # Risk trend (last 7 days)
    risk_trend = []
    for days_ago in range(6, -1, -1):
        date = datetime.now(timezone.utc) - timedelta(days=days_ago)
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        day_counts = db.query(
            ScanJob.risk_tier,
            func.count(ScanJob.id)
        ).filter(
            ScanJob.status == "completed",
            ScanJob.created_at >= day_start,
            ScanJob.created_at < day_end,
        ).group_by(ScanJob.risk_tier).all()
        
        day_data = {
            "date": day_start.strftime("%Y-%m-%d"),
            "high": 0, "medium": 0, "low": 0, "clean": 0, "unknown": 0
        }
        for tier, count in day_counts:
            if tier in day_data:
                day_data[tier] = count
        risk_trend.append(day_data)
    
    return DashboardStats(
        total_scans=total_scans,
        high_risk_count=tier_map.get("high", 0),
        medium_risk_count=tier_map.get("medium", 0),
        low_risk_count=tier_map.get("low", 0),
        clean_count=tier_map.get("clean", 0),
        top_licenses=[
            {"license": l, "tier": t, "count": c}
            for l, t, c in top_licenses
        ],
        recent_scans=recent_scans,
        risk_trend=risk_trend,
    )