"""
Semantic Drift Analyzer

Detects shifts in the meaning/intent of agent reasoning chains by
comparing run embeddings against a semantic baseline (centroid of
golden run embeddings stored in Qdrant).

Uses cosine similarity — distance from baseline centroid indicates
how far the agent's reasoning has drifted from intended behavior.
"""

import logging
import os
from typing import List, Optional, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Cosine similarity between two normalized vectors."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def cosine_distance(vec_a: List[float], vec_b: List[float]) -> float:
    """Cosine distance (1 - cosine similarity), in [0, 2]."""
    return 1.0 - cosine_similarity(vec_a, vec_b)


def compute_semantic_score(
    run_embedding: Optional[List[float]],
    baseline_embeddings: List[List[float]],
    decay_factor: float = 0.85,
) -> Dict[str, Any]:
    """
    Compute semantic drift score for a run against baseline embeddings.

    The score is based on cosine distance from the baseline centroid,
    with a decay factor to account for natural variance in golden runs.

    Args:
        run_embedding: Aggregated embedding for the current run
        baseline_embeddings: List of embeddings from golden runs
        decay_factor: Normalization factor for expected within-baseline variance

    Returns:
        dict with:
          - score: float [0, 1]
          - distance_to_centroid: raw cosine distance
          - baseline_variance: variance within golden runs
          - details
    """
    if not baseline_embeddings:
        return {
            "score": 0.0,
            "distance_to_centroid": 0.0,
            "baseline_variance": 0.0,
            "baseline_count": 0,
            "details": {"note": "No baseline embeddings available"},
        }

    if run_embedding is None:
        return {
            "score": 0.0,
            "distance_to_centroid": 0.0,
            "baseline_variance": 0.0,
            "baseline_count": len(baseline_embeddings),
            "details": {"note": "No run embedding available (no reasoning captured)"},
        }

    # Compute centroid of baseline embeddings
    baseline_array = np.array(baseline_embeddings, dtype=np.float32)
    centroid = np.mean(baseline_array, axis=0)
    # Re-normalize centroid
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm

    # Distance from current run to centroid
    distance_to_centroid = cosine_distance(run_embedding, centroid.tolist())

    # Compute within-baseline variance (to calibrate expected natural variation)
    centroid_list = centroid.tolist()
    baseline_distances = [
        cosine_distance(emb, centroid_list) for emb in baseline_embeddings
    ]
    baseline_variance = float(np.std(baseline_distances)) if baseline_distances else 0.0
    baseline_mean_dist = float(np.mean(baseline_distances)) if baseline_distances else 0.0

    # Normalize: how many standard deviations above the baseline mean?
    # Clip to [0, 1]
    std = max(baseline_variance, 0.01)  # Avoid division by zero
    z_score = (distance_to_centroid - baseline_mean_dist) / std
    # Convert z-score to [0, 1] using sigmoid-like mapping
    # z=0 → score≈0.0 (same as baseline), z=3 → score≈0.75
    normalized_score = max(0.0, min(1.0, z_score / 4.0))

    return {
        "score": round(normalized_score, 4),
        "distance_to_centroid": round(distance_to_centroid, 4),
        "baseline_mean_distance": round(baseline_mean_dist, 4),
        "baseline_variance": round(baseline_variance, 4),
        "z_score": round(z_score, 4),
        "baseline_count": len(baseline_embeddings),
    }