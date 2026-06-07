"""
Drift Detection Worker

Polls the database for unprocessed agent traces and runs the full
three-layer drift detection pipeline:

  1. Load trace from agent_traces (processed=False)
  2. Load baselines for the workflow
  3. Structural analysis (tool sequence edit distance)
  4. Semantic analysis (embedding cosine distance)
  5. Distributional analysis (CUSUM + EWMA on confidence scores)
  6. Signal fusion → composite drift score
  7. If alert: optionally generate LLM explanation
  8. Persist DriftScore, update CusumState, mark trace processed

Designed for single-node operation (no Kafka required at MVP scale).
Scale-out: replace poll loop with Kafka consumer reading from behavioral event stream.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from api.config import settings
from api.database import _make_async_url
from api.models import (
    AgentTrace, BaselineRun, DriftScore,
    CusumState as CusumStateModel, Workflow,
)
from workers.structural_analyzer import analyze_structural_drift
from workers.semantic_analyzer import analyze_semantic_drift
from workers.distributional_analyzer import (
    CusumState,
    analyze_distributional_drift,
)
from workers.signal_fusion import fuse_signals
from workers.explainability import generate_drift_explanation

logger = structlog.get_logger(__name__)


class DriftDetectionWorker:
    """
    Async worker that continuously processes unanalyzed traces.
    
    Architecture note: This runs in a separate process from the API server
    so detection never blocks API ingestion. In production, this scales
    horizontally — each worker instance processes a non-overlapping
    partition of workflow_ids.
    """

    def __init__(self):
        self.engine = create_async_engine(
            _make_async_url(settings.database_url),
            echo=False,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._running = True

    async def run(self):
        """Main worker loop — polls for unprocessed traces."""
        logger.info("worker_started", poll_interval=settings.worker_poll_interval)
        
        # Ensure tables exist
        from api.database import Base
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        while self._running:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    await asyncio.sleep(settings.worker_poll_interval)
            except Exception as exc:
                logger.error("worker_iteration_failed", error=str(exc))
                await asyncio.sleep(settings.worker_poll_interval)

    async def _process_batch(self) -> int:
        """Process a batch of unprocessed traces. Returns count processed."""
        async with self.session_factory() as db:
            result = await db.execute(
                select(AgentTrace)
                .where(AgentTrace.processed == False)
                .order_by(AgentTrace.start_time)
                .limit(settings.worker_batch_size)
            )
            traces = result.scalars().all()

            for trace in traces:
                try:
                    await self._process_trace(db, trace)
                    await db.commit()
                except Exception as exc:
                    logger.error(
                        "trace_processing_failed",
                        run_id=trace.run_id,
                        error=str(exc),
                    )
                    await db.rollback()

            return len(traces)

    async def _process_trace(self, db: AsyncSession, trace: AgentTrace):
        """Run full drift detection pipeline for a single trace."""
        run_id = trace.run_id
        workflow_id = trace.workflow_id

        logger.info("processing_trace", run_id=run_id, workflow_id=workflow_id)
        t_start = time.time()

        # Load workflow metadata
        wf_result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
        workflow = wf_result.scalar_one_or_none()
        expected_tools = workflow.expected_tools if workflow else None
        workflow_name = workflow.name if workflow else workflow_id

        # Load baselines
        baselines_result = await db.execute(
            select(BaselineRun).where(BaselineRun.workflow_id == workflow_id)
        )
        baselines = baselines_result.scalars().all()

        baseline_sequences = [b.tool_sequence for b in baselines]
        baseline_embeddings = [
            b.run_embedding for b in baselines
            if b.run_embedding is not None
        ]

        # If baselines have no embeddings yet, generate them now
        for baseline in baselines:
            if baseline.run_embedding is None:
                await self._embed_baseline(db, baseline)
                if baseline.run_embedding:
                    baseline_embeddings.append(baseline.run_embedding)

        run_tool_sequence = trace.tool_sequence or []
        run_steps = trace.steps or []

        # ── Layer 1: Structural Analysis ───────────────────────────────────
        structural = analyze_structural_drift(
            run_tool_sequence=run_tool_sequence,
            baseline_sequences=baseline_sequences,
            expected_tools=expected_tools,
        )

        # ── Layer 2: Semantic Analysis ─────────────────────────────────────
        semantic = analyze_semantic_drift(
            run_steps=run_steps,
            baseline_embeddings=baseline_embeddings,
            embedding_model=settings.embedding_model,
        )

        # ── Layer 3: Distributional Analysis (CUSUM/EWMA) ──────────────────
        cusum_state = await self._load_cusum_state(db, workflow_id)
        dist_score, dist_detail, updated_state = analyze_distributional_drift(
            run_steps=run_steps,
            state=cusum_state,
            ewma_alpha=settings.ewma_alpha,
            cusum_threshold=settings.cusum_threshold,
            cusum_slack=settings.cusum_slack,
        )
        await self._save_cusum_state(db, workflow_id, updated_state)

        # ── Signal Fusion ──────────────────────────────────────────────────
        fusion = fuse_signals(
            structural_score=structural["score"],
            semantic_score=semantic["score"],
            distributional_score=dist_score,
        )

        composite_score = fusion["composite_score"]
        alert_triggered = fusion["alert_triggered"]
        severity = fusion["severity"]

        # ── LLM Explanation (on alert only) ────────────────────────────────
        explanation = None
        if alert_triggered:
            logger.warning(
                "drift_alert",
                run_id=run_id,
                workflow_id=workflow_id,
                composite_score=composite_score,
                severity=severity,
            )
            explanation = generate_drift_explanation(
                workflow_name=workflow_name,
                composite_score=composite_score,
                severity=severity,
                structural_detail=structural.get("detail"),
                semantic_detail=semantic.get("detail"),
                distributional_detail=dist_detail,
                run_tool_sequence=run_tool_sequence,
                baseline_sequences=baseline_sequences,
            )

        # ── Persist Results ────────────────────────────────────────────────
        # Remove embedding from semantic detail before storing
        # (embeddings are large — stored separately in baseline_runs)
        semantic_detail_for_db = {
            k: v for k, v in (semantic.get("detail") or {}).items()
            if k != "embedding"
        }

        drift_score_record = DriftScore(
            run_id=run_id,
            workflow_id=workflow_id,
            structural_score=structural["score"],
            semantic_score=semantic["score"],
            distributional_score=dist_score,
            composite_score=composite_score,
            alert_triggered=alert_triggered,
            severity=severity,
            structural_detail=structural.get("detail"),
            semantic_detail=semantic_detail_for_db,
            distributional_detail=dist_detail,
            explanation=explanation,
        )
        db.add(drift_score_record)

        # Mark trace as processed
        trace.processed = True

        elapsed = (time.time() - t_start) * 1000
        logger.info(
            "trace_processed",
            run_id=run_id,
            composite_score=composite_score,
            severity=severity,
            alert=alert_triggered,
            elapsed_ms=elapsed,
        )

    async def _embed_baseline(self, db: AsyncSession, baseline: BaselineRun):
        """Generate and store embeddings for a baseline that doesn't have them yet."""
        # Load the original trace to get step outputs
        trace_result = await db.execute(
            select(AgentTrace).where(AgentTrace.run_id == baseline.run_id)
        )
        trace = trace_result.scalar_one_or_none()
        if not trace or not trace.steps:
            return

        try:
            from workers.embeddings import aggregate_run_embedding
            step_outputs = [
                s.get("output_text", "")
                for s in trace.steps
                if s.get("output_text")
            ]
            if step_outputs:
                baseline.run_embedding = aggregate_run_embedding(
                    step_outputs, model_name=settings.embedding_model
                )
                logger.info("baseline_embedded", baseline_id=baseline.id)
        except Exception as exc:
            logger.warning("baseline_embedding_failed", baseline_id=baseline.id, error=str(exc))

    async def _load_cusum_state(self, db: AsyncSession, workflow_id: str) -> CusumState:
        """Load persisted CUSUM state for a workflow."""
        result = await db.execute(
            select(CusumStateModel).where(CusumStateModel.workflow_id == workflow_id)
        )
        record = result.scalar_one_or_none()
        
        if record is None:
            return CusumState()
        
        return CusumState(
            cusum_pos=record.cusum_pos or 0.0,
            cusum_neg=record.cusum_neg or 0.0,
            ewma_value=record.ewma_value,
            baseline_mean=record.baseline_mean,
            baseline_std=record.baseline_std,
            sample_count=record.sample_count or 0,
        )

    async def _save_cusum_state(
        self,
        db: AsyncSession,
        workflow_id: str,
        state: CusumState,
    ):
        """Persist updated CUSUM state for a workflow."""
        result = await db.execute(
            select(CusumStateModel).where(CusumStateModel.workflow_id == workflow_id)
        )
        record = result.scalar_one_or_none()

        if record is None:
            record = CusumStateModel(workflow_id=workflow_id)
            db.add(record)

        record.cusum_pos = state.cusum_pos
        record.cusum_neg = state.cusum_neg
        record.ewma_value = state.ewma_value
        record.baseline_mean = state.baseline_mean
        record.baseline_std = state.baseline_std
        record.sample_count = state.sample_count

    def stop(self):
        self._running = False


async def main():
    worker = DriftDetectionWorker()
    try:
        await worker.run()
    except KeyboardInterrupt:
        worker.stop()
        logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())