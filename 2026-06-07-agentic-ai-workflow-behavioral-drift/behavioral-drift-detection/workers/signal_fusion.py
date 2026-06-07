"""
Signal Fusion Layer

Combines structural, semantic, and distributional drift scores into a single
composite drift score and determines alert severity.

Weights are configurable via environment variables (see config.py).
"""

from __future__ import annotations

from api.config import settings


def classify_severity(score: float, threshold: float) -> str:
    """
    Map composite drift score to severity tier.
    
    Tiers are calibrated around the alert threshold:
      - low:      score < 0.4 * threshold
      - medium:   0.4 <= score < threshold
      - high:     threshold <= score < 1.3 * threshold (capped at 1.0)
      - critical: score >= min(1.3 * threshold, 1.0)
    """
    low_bound = 0.4 * threshold
    high_bound = min(1.3 * threshold, 1.0)
    
    if score < low_bound:
        return "low"
    elif score < threshold:
        return "medium"
    elif score < high_bound:
        return "high"
    else:
        return "critical"


def fuse_signals(
    structural_score: float,
    semantic_score: float,
    distributional_score: float,
    structural_weight: float = None,
    semantic_weight: float = None,
    distributional_weight: float = None,
    alert_threshold: float = None,
) -> dict:
    """
    Compute weighted composite drift score and alert classification.
    
    Args:
        structural_score: [0,1] — tool sequence / step order deviation
        semantic_score: [0,1] — cosine distance from baseline embedding cluster
        distributional_score: [0,1] — CUSUM/EWMA confidence distribution shift
        *_weight: Optional weight overrides (defaults from settings)
        alert_threshold: Alert trigger threshold (default from settings)
    
    Returns dict with:
        composite_score: float [0, 1]
        alert_triggered: bool
        severity: "low" | "medium" | "high" | "critical"
        weights_used: the weight configuration applied
    """
    sw = structural_weight if structural_weight is not None else settings.structural_weight
    ew = semantic_weight if semantic_weight is not None else settings.semantic_weight
    dw = distributional_weight if distributional_weight is not None else settings.distributional_weight
    threshold = alert_threshold if alert_threshold is not None else settings.drift_alert_threshold

    # Normalize weights (in case they don't sum to 1)
    total = sw + ew + dw
    if total <= 0:
        total = 1.0
    sw, ew, dw = sw / total, ew / total, dw / total

    composite = sw * structural_score + ew * semantic_score + dw * distributional_score
    composite = float(min(max(composite, 0.0), 1.0))

    alert_triggered = composite >= threshold
    severity = classify_severity(composite, threshold)

    return {
        "composite_score": composite,
        "alert_triggered": alert_triggered,
        "severity": severity,
        "weights_used": {
            "structural": sw,
            "semantic": ew,
            "distributional": dw,
        },
    }