"""
Celery worker for async quality scoring and drift detection.
"""
import os
import json
import uuid
import structlog
from datetime import datetime, timezone, timedelta
from celery import Celery
from celery.schedules import crontab

from app.config import settings

logger = structlog.get_logger()

# Initialize Celery
celery_app = Celery(
    "promptmonitor",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "run-drift-detection": {
            "task": "app.worker.run_drift_detection_all",
            "schedule": 300.0,  # every 5 minutes
        },
        "aggregate-metrics": {
            "task": "app.worker.aggregate_metrics",
            "schedule": 3600.0,  # every hour
        },
    },
)

# Use celery_app as the module-level 'app' for celery CLI
app = celery_app


def get_db_session():
    from app.database import SyncSessionLocal
    return SyncSessionLocal()


@celery_app.task(name="app.worker.score_inference_async", bind=True, max_retries=3)
def score_inference_async(
    self,
    template_name: str,
    request_payload: dict,
    response_payload: dict,
    output_text: str,
    model: str,
    prompt_tokens: int = None,
    completion_tokens: int = None,
    latency_ms: float = None,
):
    """Score a single inference log entry."""
    from app.models import InferenceLog, PromptTemplate, QualityScore
    from app.scorer import QualityScorer
    from sqlalchemy import select

    db = get_db_session()
    try:
        # Get or create template
        template = db.execute(
            select(PromptTemplate).where(PromptTemplate.name == template_name)
        ).scalar_one_or_none()

        if not template:
            template = PromptTemplate(name=template_name)
            db.add(template)
            db.flush()

        # Create inference log
        log = InferenceLog(
            template_id=template.id,
            template_name=template_name,
            request_payload=request_payload,
            response_payload=response_payload,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            status="scoring",
        )
        db.add(log)
        db.flush()

        log_id = log.id
        template_id = template.id

        # Score the output
        scorer = QualityScorer(db)
        scores = scorer.score(
            template_id=template_id,
            output_text=output_text,
            request_payload=request_payload,
            response_payload=response_payload,
        )

        # Save scores
        for metric_name, score_value, meta in scores:
            qs = QualityScore(
                inference_log_id=log_id,
                template_id=template_id,
                metric_name=metric_name,
                score=score_value,
                metadata_=meta,
            )
            db.add(qs)

        log.status = "scored"
        db.commit()

        logger.info(
            "inference_scored",
            template=template_name,
            log_id=str(log_id),
            metrics=[(n, round(s, 3)) for n, s, _ in scores],
        )

        # Trigger drift detection for this template
        run_drift_detection.apply_async(
            kwargs={"template_id": str(template_id)},
            countdown=5,
        )

    except Exception as e:
        db.rollback()
        logger.error("scoring_failed", error=str(e), template=template_name)
        raise self.retry(exc=e, countdown=30)
    finally:
        db.close()


@celery_app.task(name="app.worker.run_drift_detection", bind=True)
def run_drift_detection(self, template_id: str):
    """Run drift detection for a specific template."""
    from app.detector import DriftDetector
    from app.models import PromptTemplate
    from sqlalchemy import select

    db = get_db_session()
    try:
        template = db.get(PromptTemplate, uuid.UUID(template_id))
        if not template:
            return

        detector = DriftDetector(db)
        alerts = detector.detect(template)

        if alerts:
            from app.alerting import AlertRouter
            router = AlertRouter()
            for alert in alerts:
                router.send_alert(alert)

        logger.info(
            "drift_detection_complete",
            template=template.name,
            alerts_generated=len(alerts),
        )
    except Exception as e:
        logger.error("drift_detection_failed", error=str(e))
    finally:
        db.close()


@celery_app.task(name="app.worker.run_drift_detection_all")
def run_drift_detection_all():
    """Run drift detection for all templates."""
    from app.models import PromptTemplate
    from sqlalchemy import select

    db = get_db_session()
    try:
        templates = db.execute(select(PromptTemplate)).scalars().all()
        for template in templates:
            run_drift_detection.apply_async(
                kwargs={"template_id": str(template.id)},
            )
        logger.info("scheduled_drift_detection", template_count=len(templates))
    except Exception as e:
        logger.error("scheduled_drift_detection_failed", error=str(e))
    finally:
        db.close()


@celery_app.task(name="app.worker.aggregate_metrics")
def aggregate_metrics():
    """Aggregate quality metrics into hourly buckets."""
    from app.models import QualityScore, MetricAggregate, PromptTemplate
    from sqlalchemy import select, func, text
    import numpy as np

    db = get_db_session()
    try:
        # Aggregate last 2 hours
        now = datetime.now(timezone.utc)
        window_end = now.replace(minute=0, second=0, microsecond=0)
        window_start = window_end - timedelta(hours=2)

        # Get all template+metric combinations with recent scores
        results = db.execute(
            select(
                QualityScore.template_id,
                QualityScore.metric_name,
                func.array_agg(QualityScore.score).label("scores"),
                func.count(QualityScore.id).label("count"),
            )
            .where(QualityScore.scored_at >= window_start)
            .where(QualityScore.scored_at < window_end)
            .group_by(QualityScore.template_id, QualityScore.metric_name)
        ).all()

        for row in results:
            scores_arr = np.array(row.scores, dtype=float)
            existing = db.execute(
                select(MetricAggregate).where(
                    MetricAggregate.template_id == row.template_id,
                    MetricAggregate.metric_name == row.metric_name,
                    MetricAggregate.window_start == window_start,
                )
            ).scalar_one_or_none()

            agg_data = dict(
                template_id=row.template_id,
                metric_name=row.metric_name,
                window_start=window_start,
                window_end=window_end,
                sample_count=int(row.count),
                mean_score=float(np.mean(scores_arr)),
                std_score=float(np.std(scores_arr)),
                min_score=float(np.min(scores_arr)),
                max_score=float(np.max(scores_arr)),
                p10_score=float(np.percentile(scores_arr, 10)),
                p50_score=float(np.percentile(scores_arr, 50)),
                p90_score=float(np.percentile(scores_arr, 90)),
            )

            if existing:
                for k, v in agg_data.items():
                    setattr(existing, k, v)
            else:
                db.add(MetricAggregate(**agg_data))

        db.commit()
        logger.info("metrics_aggregated", windows=len(results))
    except Exception as e:
        db.rollback()
        logger.error("metric_aggregation_failed", error=str(e))
    finally:
        db.close()