import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import redis

from app.database import get_db
from app.models import CorpusSnippet
from app.schemas import HealthResponse
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    # Check database
    db_status = "ok"
    corpus_size = 0
    try:
        corpus_size = db.query(CorpusSnippet).count()
    except Exception as e:
        db_status = f"error: {str(e)[:50]}"

    # Check Redis
    redis_status = "ok"
    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        r.close()
    except Exception as e:
        redis_status = f"error: {str(e)[:50]}"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(
        status=overall,
        version="1.0.0",
        database=db_status,
        redis=redis_status,
        corpus_size=corpus_size,
    )