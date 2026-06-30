"""
Distributional Drift Analyzer

Detects sustained shifts in output distributions using:
- CUSUM (Cumulative Sum Control Chart): detects persistent directional shifts
- EWMA (Exponentially Weighted Moving Average): tracks trends over time
- Confidence score distribution analysis

These are classical Statistical Process Control methods adapted for
agent behavioral monitoring. No LLM-in-the-loop required.
"""

import logging
import math
from typing import List, Optional, Dict, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class CUSUMDetector:
    """
    Two-sided CUSUM detector for detecting mean shifts in a signal.

    The CUSUM test accumulates deviations from a target mean.
    When the cumulative sum exceeds a threshold H, a shift is detected.

    Reference: Page (1954), "Continuous Inspection Schemes"
    """

    def __init__(self, k: float = 0.5, h: float = 5.0):
        """
        Args:
            k: Allowance parameter (slack) — half the magnitude of shift to detect
            h: Decision threshold — higher = less sensitive to small shifts
        """
        self.k = k
        self.h = h
        self.cusum_pos = 0.0  # Upward CUSUM
        self.cusum_neg = 0.0  # Downward CUSUM

    def update(self, value: float, target: float, sigma: float = 1.0) -> Tuple[float, bool]:
        """
        Update CUSUM with a new observation.

        Returns:
            (max_cusum, is_alarm): normalized CUSUM value and whether threshold exceeded
        """
        if sigma <= 0:
            sigma = 1.0

        standardized = (value - target) / sigma
        self.cusum_pos = max(0, self.cusum_pos + standardized - self.k)
        self.cusum_neg = max(0, self.cusum_neg - standardized - self.k)

        max_cusum = max(self.cusum_pos, self.cusum_neg)
        is_alarm = max_cusum > self.h

        return max_cusum, is_alarm

    def reset(self):
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0

    @property
    def normalized_score(self) -> float:
        """Normalize current CUSUM to [0, 1] relative to threshold."""
        max_val = max(self.cusum_pos, self.cusum_neg)
        return min(max_val / max(self.h, 1.0), 1.0)


class EWMADetector:
    """
    Exponentially Weighted Moving Average detector.

    Smooths the signal and detects deviations from baseline mean.
    More sensitive to gradual drift than CUSUM.
    """

    def __init__(self, lambda_: float = 0.2, l_sigma: float = 3.0):
        """
        Args:
            lambda_: Smoothing parameter (0 = ignore new data, 1 = only new data)
            l_sigma: Control limit multiplier (number of sigmas)
        """
        self.lambda_ = lambda_
        self.l_sigma = l_sigma
        self.ewma: Optional[float] = None
        self.variance_ewma: Optional[float] = None

    def update(self, value: float, target: float, sigma: float = 1.0) -> Tuple[float, bool]:
        """
        Update EWMA with a new observation.

        Returns:
            (deviation_normalized, is_alarm)
        """
        if self.ewma is None:
            self.ewma = target
            self.variance_ewma = sigma ** 2

        self.ewma = self.lambda_ * value + (1 - self.lambda_) * self.ewma

        # Asymptotic variance of EWMA
        ewma_sigma = sigma * math.sqrt(
            self.lambda_ / (2 - self.lambda_)
        )

        deviation = abs(self.ewma - target)
        control_limit = self.l_sigma * max(ewma_sigma, 1e-6)
        is_alarm = deviation > control_limit

        normalized = min(deviation / max(control_limit, 1e-6), 1.0)
        return normalized, is_alarm


def compute_distributional_score(
    current_confidence: Optional[float],
    current_token_count: Optional[int],
    current_latency_ms: Optional[float],
    baseline_confidences: List[float],
    baseline_token_counts: List[float],
    recent_confidences: List[float],  # Last N runs (for CUSUM/EWMA)
    recent_token_counts: List[float],
) -> Dict[str, Any]:
    """
    Compute distributional drift score using CUSUM and EWMA.

    Analyzes:
    1. Confidence score drift (agent becoming less/more certain)
    2. Token count drift (output length changing systematically)
    3. Latency patterns (optional)

    Returns:
        dict with score [0,1] and detailed breakdown
    """
    scores = []
    details = {}

    # ── Confidence score analysis ──────────────────────────────────────────────
    if current_confidence is not None and len(baseline_confidences) >= 3:
        baseline_mean = float(np.mean(baseline_confidences))
        baseline_std = float(np.std(baseline_confidences)) or 0.1

        # CUSUM on recent confidence values
        cusum = CUSUMDetector(k=0.5, h=4.0)
        for c in recent_confidences[-10:]:  # Last 10 observations
            cusum.update(c, baseline_mean, baseline_std)
        # Update with current
        cusum.update(current_confidence, baseline_mean, baseline_std)
        cusum_score = cusum.normalized_score

        # EWMA on recent confidence values
        ewma = EWMADetector(lambda_=0.3, l_sigma=2.5)
        for c in recent_confidences[-10:]:
            ewma.update(c, baseline_mean, baseline_std)
        ewma_score, ewma_alarm = ewma.update(
            current_confidence, baseline_mean, baseline_std
        )

        confidence_drift = 0.6 * cusum_score + 0.4 * ewma_score
        scores.append(confidence_drift)
        details["confidence"] = {
            "current": current_confidence,
            "baseline_mean": round(baseline_mean, 4),
            "baseline_std": round(baseline_std, 4),
            "cusum_score": round(cusum_score, 4),
            "ewma_score": round(ewma_score, 4),
            "drift": round(confidence_drift, 4),
        }

    # ── Token count analysis ───────────────────────────────────────────────────
    if current_token_count is not None and len(baseline_token_counts) >= 3:
        baseline_mean_tc = float(np.mean(baseline_token_counts))
        baseline_std_tc = float(np.std(baseline_token_counts)) or 10.0

        cusum_tc = CUSUMDetector(k=0.5, h=4.0)
        for tc in recent_token_counts[-10:]:
            cusum_tc.update(tc, baseline_mean_tc, baseline_std_tc)
        cusum_tc.update(current_token_count, baseline_mean_tc, baseline_std_tc)
        tc_drift = cusum_tc.normalized_score
        scores.append(tc_drift * 0.5)  # Token count is lower weight
        details["token_count"] = {
            "current": current_token_count,
            "baseline_mean": round(baseline_mean_tc, 2),
            "cusum_score": round(tc_drift, 4),
        }

    # ── Confidence deviation (simple, for when we have few baselines) ─────────
    if current_confidence is not None and 1 <= len(baseline_confidences) < 3:
        baseline_mean = float(np.mean(baseline_confidences))
        simple_drift = abs(current_confidence - baseline_mean)
        scores.append(simple_drift)
        details["confidence_simple"] = {
            "current": current_confidence,
            "baseline_mean": round(baseline_mean, 4),
            "drift": round(simple_drift, 4),
        }

    if not scores:
        return {
            "score": 0.0,
            "baseline_count": len(baseline_confidences),
            "details": {"note": "Insufficient data for distributional analysis"},
        }

    composite = float(np.mean(scores))

    return {
        "score": round(min(composite, 1.0), 4),
        "baseline_count": len(baseline_confidences),
        "details": details,
    }