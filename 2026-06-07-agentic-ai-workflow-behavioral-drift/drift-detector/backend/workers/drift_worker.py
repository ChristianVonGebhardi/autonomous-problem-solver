"""
Drift Detection Worker

Polls for unprocessed trace runs and computes drift scores.
Uses asyncio event loop — no Kafka needed at MVP scale.

Run: python -m backend.workers.drift_worker
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from backend.db.database import AsyncSessionLocal
from backend.db.models import Workflow, TraceRun, SpanRecord, DriftScore, Alert
from backend.detection.structural import compute_structural_score
from backend.detection.semantic import compute_semantic_score
from backend.detection.distributional import compute_distributional_score
from backend.detection.fusion import fuse_drift_signals
from backend.detection.explainability import generate_explanation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("drift_worker")

POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "5"))
DETECTION_WINDOW = int(os.getenv("DETECTION_WINDOW_SIZE", "10"))


async def get_baseline_data(
    session, workflow_id: str
) -> Dict[str, Any]:
    """Fetch baseline traces for a workflow."""
    result = await session.execute(
        select(TraceRun)
        .where(
            and_(
                TraceRun.workflow_id == workflow_id,
                TraceRun.is_baseline == True,
            )
        )
        .order_by(TraceRun.start_time.asc())
    )
    baselines = result.scalars().all()

    return {
        "tool_sequences": [b.tool_sequence or [] for b in baselines],
        "step_sequences": [b.step_sequence or [] for b in baselines],
        "embeddings": [b.run_embedding for b in baselines if b.run_embedding],
        "confidences": [b.avg_confidence for b in baselines if b.avg_confidence is not None],
        "count": len(baselines),
    }


async def get_recent_run_data(
    session, workflow_id: str, window: int = 10
) -> Dict[str, Any]:
    """Fetch recent (non-baseline) run metrics for CUSUM/EWMA."""
    result = await session.execute(
        select(TraceRun)
        .where(
            and_(
                TraceRun.workflow_id == workflow_id,
                TraceRun.is_baseline == False,
            )
        )
        .order_by(TraceRun.start_time.desc())
        .limit(window)
    )
    recent = result.scalars().all()

    return {
        "confidences": [
            r.avg_confidence for r in recent if r.avg_confidence is not None
        ],
        "token_counts": [],  # Would sum span token counts
    }


async def process_trace_run(session, run: TraceRun) -> Optional[DriftScore]:
    """Run all three drift analyzers and persist the result."""

    # 1. Fetch baseline data
    baseline_data = await get_baseline_data(session, run.workflow_id)

    if baseline_data["count"] == 0:
        logger.info(
            f"Skipping drift for {run.run_id} — no baselines for {run.workflow_id}"
        )
        # Create a zero-score record so we don't keep reprocessing
        drift = DriftScore(
            workflow_id=run.workflow_id,
            run_id=run.run_id,
            timestamp=datetime.utcnow(),
            structural_score=0.0,
            semantic_score=0.0,
            distributional_score=0.0,
            composite_score=0.0,
            alert_level="normal",
            details={"note": "No baselines available — run is being used as first run"},
        )
        return drift

    # 2. Fetch recent runs for CUSUM context
    recent_data = await get_recent_run_data(session, run.workflow_id, DETECTION_WINDOW)

    # 3. Structural analysis
    structural_result = compute_structural_score(
        current_tool_sequence=run.tool_sequence or [],
        current_step_sequence=run.step_sequence or [],
        baseline_tool_sequences=baseline_data["tool_sequences"],
        baseline_step_sequences=baseline_data["step_sequences"],
    )

    # 4. Semantic analysis
    semantic_result = compute_semantic_score(
        run_embedding=run.run_embedding,
        baseline_embeddings=baseline_data["embeddings"],
    )

    # 5. Distributional analysis
    distributional_result = compute_distributional_score(
        current_confidence=run.avg_confidence,
        current_token_count=None,
        current_latency_ms=None,
        baseline_confidences=baseline_data["confidences"],
        baseline_token_counts=[],
        recent_confidences=recent_data["confidences"],
        recent_token_counts=[],
    )

    # 6. Fuse signals
    drift_result = fuse_drift_signals(
        workflow_id=run.workflow_id,
        run_id=run.run_id,
        structural_result=structural_result,
        semantic_result=semantic_result,
        distributional_result=distributional_result,
    )

    logger.info(
        f"[{run.workflow_id}] run={run.run_id[:8]}... "
        f"composite={drift_result.composite_score:.3f} "
        f"level={drift_result.alert_level}"
    )

    # 7. Persist drift score
    drift = DriftScore(
        workflow_id=run.workflow_id,
        run_id=run.run_id,
        timestamp=datetime.utcnow(),
        structural_score=drift_result.structural_score,
        semantic_score=drift_result.semantic_score,
        distributional_score=drift_result.distributional_score,
        composite_score=drift_result.composite_score,
        alert_level=drift_result.alert_level,
        details={
            "structural": drift_result.structural_details,
            "semantic": drift_result.semantic_details,
            "distributional": drift_result.distributional_details,
            "weights": drift_result.weights_used,
        },
    )
    session.add(drift)

    # 8. Create alert if needed
    if drift_result.alert_level in ("warning", "alert"):
        existing = await session.execute(
            select(Alert).where(
                and_(
                    Alert.workflow_id == run.workflow_id,
                    Alert.run_id == run.run_id,
                )
            )
        )
        if existing.scalar_one_or_none() is None:
            explanation = await generate_explanation(
                workflow_id=run.workflow_id,
                run_id=run.run_id,
                composite_score=drift_result.composite_score,
                alert_level=drift_result.alert_level,
                structural_score=drift_result.structural_score,
                semantic_score=drift_result.semantic_score,
                distributional_score=drift_result.distributional_score,
                structural_details=drift_result.structural_details,
                semantic_details=drift_result.semantic_details,
                distributional_details=drift_result.distributional_details,
            )

            alert = Alert(
                workflow_id=run.workflow_id,
                run_id=run.run_id,
                alert_level=drift_result.alert_level,
                composite_score=drift_result.composite_score,
                structural_score=drift_result.structural_score,
                semantic_score=drift_result.semantic_score,
                distributional_score=drift_result.distributional_score,
                explanation=explanation,
                acknowledged=False,
                created_at=datetime.utcnow(),
            )
            session.add(alert)
            logger.warning(
                f"🚨 ALERT [{drift_result.alert_level.upper()}] "
                f"{run.workflow_id} — composite={drift_result.composite_score:.3f}"
            )

    return drift


async def worker_loop():
    """Main worker loop — polls for unprocessed traces."""
    logger.info(f"Drift detection worker starting (poll interval: {POLL_INTERVAL}s)")

    while True:
        try:
            async with AsyncSessionLocal() as session:
                # Find runs without drift scores
                scored_subq = select(DriftScore.run_id)
                result = await session.execute(
                    select(TraceRun)
                    .where(
                        and_(
                            TraceRun.is_baseline == False,
                            ~TraceRun.run_id.in_(scored_subq),
                        )
                    )
                    .order_by(TraceRun.created_at.asc())
                    .limit(20)
                )
                pending_runs = result.scalars().all()

                if pending_runs:
                    logger.info(f"Processing {len(pending_runs)} pending runs...")
                    for run in pending_runs:
                        try:
                            drift = await process_trace_run(session, run)
                            if drift:
                                session.add(drift)
                        except Exception as e:
                            logger.error(f"Error processing run {run.run_id}: {e}", exc_info=True)

                    await session.commit()
                    logger.info("Batch committed.")

        except Exception as e:
            logger.error(f"Worker loop error: {e}", exc_info=True)

        await asyncio.sleep(POLL_INTERVAL)


async def main():
    """Initialize DB then start worker."""
    from backend.db.database import engine, Base
    from backend.db import models  # noqa

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified.")

    await worker_loop()


if __name__ == "__main__":
    asyncio.run(main())