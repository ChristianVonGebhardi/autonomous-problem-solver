"""
Semantic Drift Analyzer

Detects drift in the embedding-space representation of agent reasoning:
  - Computes mean-pooled embedding of the run's step outputs
  - Compares to baseline run embeddings using cosine distance
  - Reports the minimum distance to any approved baseline
    (nearest-neighbor approach supports multiple valid behavioral modes)

Operates entirely locally using sentence-transformers — no LLM API calls.
"""

from __future__ import annotations

from typing import Optional
import structlog

from workers.embeddings import (
    aggregate_run_embedding,
    mean_cosine_distance_to_baselines,
    cosine_distance,
)

logger = structlog.get_logger(__name__)


def _extract_step_outputs(steps: list[dict]) -> list[str]:
    """Extract non-empty output texts from step data."""
    outputs = []
    for step in steps:
        text = step.get("output_text") or ""
        if text.strip():
            outputs.append(text.strip())
    return outputs


def analyze_semantic_drift(
    run_steps: list[dict],
    baseline_embeddings: list[list[float]],
    embedding_model: str = "all-MiniLM-L6-v2",
) -> dict:
    """
    Compute semantic drift score by comparing run embedding to baseline cluster.
    
    Args:
        run_steps: List of step dicts from the trace (with output_text fields).
        baseline_embeddings: List of run-level embedding vectors from golden runs.
        embedding_model: Name of sentence-transformers model to use.
    
    Returns dict with:
        score: float in [0, 1] — 0 is no drift, 1 is maximum semantic drift
        embedding: the computed run embedding (stored for future baseline use)
        detail: breakdown
    """
    step_outputs = _extract_step_outputs(run_steps)
    
    if not step_outputs:
        return {
            "score": 0.0,
            "embedding": None,
            "detail": {
                "reason": "no_output_text",
                "cosine_distance": None,
                "step_output_count": 0,
            }
        }

    # Compute run-level embedding (mean-pooled over steps)
    try:
        run_embedding = aggregate_run_embedding(step_outputs, model_name=embedding_model)
    except Exception as exc:
        logger.warning("embedding_failed", error=str(exc))
        return {
            "score": 0.0,
            "embedding": None,
            "detail": {"reason": f"embedding_error: {exc}"},
        }

    if run_embedding is None:
        return {
            "score": 0.0,
            "embedding": None,
            "detail": {"reason": "embedding_returned_none"},
        }

    if not baseline_embeddings:
        return {
            "score": 0.0,
            "embedding": run_embedding,
            "detail": {
                "reason": "no_baselines",
                "cosine_distance": None,
                "step_output_count": len(step_outputs),
            }
        }

    # Compare to baseline cluster
    min_distance = mean_cosine_distance_to_baselines(run_embedding, baseline_embeddings)
    
    # Individual distances to each baseline for detail
    individual_distances = [
        float(cosine_distance(run_embedding, b))
        for b in baseline_embeddings
    ]

    logger.debug(
        "semantic_analysis",
        min_cosine_distance=min_distance,
        step_output_count=len(step_outputs),
        baseline_count=len(baseline_embeddings),
    )

    return {
        "score": float(min_distance),
        "embedding": run_embedding,
        "detail": {
            "min_cosine_distance": float(min_distance),
            "individual_distances": individual_distances,
            "step_output_count": len(step_outputs),
            "baseline_count": len(baseline_embeddings),
        }
    }