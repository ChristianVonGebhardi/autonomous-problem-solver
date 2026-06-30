"""
Signal Fusion Layer

Combines structural, semantic, and distributional drift scores into
a unified composite drift score with configurable weights.

Also handles alert level classification and cooldown logic.
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default weights (configurable via env)
DEFAULT_STRUCTURAL_WEIGHT = float(os.getenv("STRUCTURAL_WEIGHT", "0.35"))
DEFAULT_SEMANTIC_WEIGHT = float(os.getenv("SEMANTIC_WEIGHT", "0.40"))
DEFAULT_DISTRIBUTIONAL_WEIGHT = float(os.getenv("DISTRIBUTIONAL_WEIGHT", "0.25"))

DRIFT_WARN_THRESHOLD = float(os.getenv("DRIFT_WARN_THRESHOLD", "0.40"))
DRIFT_ALERT_THRESHOLD = float(os.getenv("DRIFT_ALERT_THRESHOLD", "0.65"))


@dataclass
class DriftResult:
    """Complete drift analysis result for a single run."""
    workflow_id: str
    run_id: str
    structural_score: float
    semantic_score: float
    distributional_score: float
    composite_score: float
    alert_level: str  # "normal" | "warning" | "alert"
    structural_details: Dict[str, Any]
    semantic_details: Dict[str, Any]
    distributional_details: Dict[str, Any]
    weights_used: Dict[str, float]


def compute_composite_score(
    structural_score: float,
    semantic_score: float,
    distributional_score: float,
    structural_weight: float = DEFAULT_STRUCTURAL_WEIGHT,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
    distributional_weight: float = DEFAULT_DISTRIBUTIONAL_WEIGHT,
) -> float:
    """
    Weighted combination of the three drift signal layers.

    Weights should sum to 1.0. If they don't, they are normalized.
    """
    total_weight = structural_weight + semantic_weight + distributional_weight
    if total_weight <= 0:
        return 0.0

    composite = (
        structural_weight * structural_score
        + semantic_weight * semantic_score
        + distributional_weight * distributional_score
    ) / total_weight

    return round(min(max(composite, 0.0), 1.0), 4)


def classify_alert_level(composite_score: float) -> str:
    """
    Classify composite drift score into alert levels.

    Returns:
        "normal" | "warning" | "alert"
    """
    if composite_score >= DRIFT_ALERT_THRESHOLD:
        return "alert"
    elif composite_score >= DRIFT_WARN_THRESHOLD:
        return "warning"
    else:
        return "normal"


def fuse_drift_signals(
    workflow_id: str,
    run_id: str,
    structural_result: Dict[str, Any],
    semantic_result: Dict[str, Any],
    distributional_result: Dict[str, Any],
) -> DriftResult:
    """
    Fuse all three drift signal layers into a unified result.

    Args:
        workflow_id: Workflow identifier
        run_id: Current run identifier
        structural_result: Output from structural analyzer
        semantic_result: Output from semantic analyzer
        distributional_result: Output from distributional analyzer

    Returns:
        DriftResult with composite score and alert classification
    """
    structural_score = float(structural_result.get("score", 0.0))
    semantic_score = float(semantic_result.get("score", 0.0))
    distributional_score = float(distributional_result.get("score", 0.0))

    composite = compute_composite_score(
        structural_score,
        semantic_score,
        distributional_score,
    )

    alert_level = classify_alert_level(composite)

    logger.debug(
        f"Drift fusion for {workflow_id}/{run_id}: "
        f"structural={structural_score:.3f}, "
        f"semantic={semantic_score:.3f}, "
        f"distributional={distributional_score:.3f}, "
        f"composite={composite:.3f}, "
        f"level={alert_level}"
    )

    return DriftResult(
        workflow_id=workflow_id,
        run_id=run_id,
        structural_score=structural_score,
        semantic_score=semantic_score,
        distributional_score=distributional_score,
        composite_score=composite,
        alert_level=alert_level,
        structural_details=structural_result,
        semantic_details=semantic_result,
        distributional_details=distributional_result,
        weights_used={
            "structural": DEFAULT_STRUCTURAL_WEIGHT,
            "semantic": DEFAULT_SEMANTIC_WEIGHT,
            "distributional": DEFAULT_DISTRIBUTIONAL_WEIGHT,
        },
    )