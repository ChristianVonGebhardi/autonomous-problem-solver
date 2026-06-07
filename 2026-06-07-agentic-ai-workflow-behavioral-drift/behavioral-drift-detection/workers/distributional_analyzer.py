"""
Distributional Drift Analyzer — CUSUM + EWMA

Detects shifts in the distribution of confidence scores and output characteristics
over time using classical Statistical Process Control (SPC) algorithms:

  CUSUM (Cumulative Sum):
    - Accumulates signed deviations from baseline mean
    - Detects sustained shifts faster than threshold crossing
    - Two-sided: detects both upward and downward shifts
    - Classic Page-Hinkley / Wald formulation

  EWMA (Exponentially Weighted Moving Average):
    - Gives more weight to recent observations
    - Smooth trend signal complementary to CUSUM's abrupt-change detection
    - alpha parameter controls recency bias (higher = more reactive)

These algorithms run on per-workflow state persisted in CusumState table,
so the worker correctly resumes after restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CusumState:
    """Mutable CUSUM + EWMA state for one workflow."""
    cusum_pos: float = 0.0
    cusum_neg: float = 0.0
    ewma_value: Optional[float] = None
    baseline_mean: Optional[float] = None
    baseline_std: Optional[float] = None
    sample_count: int = 0


def update_ewma(previous: Optional[float], observation: float, alpha: float) -> float:
    """
    EWMA update: S_t = alpha * x_t + (1 - alpha) * S_{t-1}
    
    alpha in (0, 1]: higher = more reactive to recent changes
    """
    if previous is None:
        return observation
    return alpha * observation + (1.0 - alpha) * previous


def update_cusum(
    cusum_pos: float,
    cusum_neg: float,
    observation: float,
    mean: float,
    std: float,
    k: float,  # slack (allowance) — typically 0.5 * shift_to_detect in sigma units
) -> tuple[float, float]:
    """
    Two-sided CUSUM update (Page 1954).
    
    Accumulates deviation above (cusum_pos) and below (cusum_neg) the mean.
    k is the slack parameter — small deviations within k*std are ignored.
    
    Returns (new_cusum_pos, new_cusum_neg).
    """
    if std <= 0:
        std = 1.0
    
    # Standardize observation
    z = (observation - mean) / std
    
    cusum_pos = max(0.0, cusum_pos + z - k)
    cusum_neg = max(0.0, cusum_neg - z - k)
    
    return cusum_pos, cusum_neg


def compute_distributional_score(
    cusum_pos: float,
    cusum_neg: float,
    ewma_value: float,
    baseline_mean: float,
    cusum_threshold: float,
) -> float:
    """
    Map CUSUM and EWMA signals to a [0, 1] drift score.
    
    Logic:
    - If CUSUM exceeds threshold, score = 1.0 (definitive shift detected)
    - Otherwise, scale linearly based on CUSUM accumulation and EWMA deviation
    """
    max_cusum = max(cusum_pos, cusum_neg)
    
    # How far along to the detection threshold?
    cusum_ratio = min(max_cusum / max(cusum_threshold, 1.0), 1.0)
    
    # EWMA deviation from baseline mean (normalized)
    if baseline_mean is not None and baseline_mean != 0:
        ewma_deviation = abs(ewma_value - baseline_mean) / (abs(baseline_mean) + 1e-6)
        ewma_deviation = min(ewma_deviation, 1.0)
    else:
        ewma_deviation = 0.0
    
    # Weighted combination: CUSUM is primary signal, EWMA is secondary
    score = 0.70 * cusum_ratio + 0.30 * ewma_deviation
    return float(min(score, 1.0))


def analyze_distributional_drift(
    run_steps: list[dict],
    state: CusumState,
    ewma_alpha: float = 0.3,
    cusum_threshold: float = 5.0,
    cusum_slack: float = 1.0,
) -> tuple[float, dict, CusumState]:
    """
    Run CUSUM + EWMA analysis on confidence scores from this run.
    
    Args:
        run_steps: Step dicts containing optional confidence scores.
        state: Current persisted CUSUM/EWMA state for this workflow.
        ewma_alpha: EWMA smoothing factor.
        cusum_threshold: CUSUM detection threshold (in sigma units).
        cusum_slack: CUSUM slack/allowance parameter.
    
    Returns:
        (score, detail_dict, updated_state)
    """
    # Extract confidence scores from steps
    confidences = [
        step["confidence"]
        for step in run_steps
        if step.get("confidence") is not None
    ]
    
    # Use step count as a signal if no confidence available
    if not confidences:
        # Fall back to step count signal
        signal_value = float(len(run_steps))
        signal_source = "step_count"
    else:
        signal_value = sum(confidences) / len(confidences)
        signal_source = "mean_confidence"

    state.sample_count += 1

    # Bootstrap baseline from first few samples
    if state.baseline_mean is None:
        if state.sample_count <= 5:
            # Accumulating initial samples — no drift score yet
            state.ewma_value = update_ewma(state.ewma_value, signal_value, ewma_alpha)
            state.baseline_mean = signal_value
            state.baseline_std = 0.1  # prior std
            return 0.0, {
                "reason": "bootstrapping_baseline",
                "sample_count": state.sample_count,
                "signal_value": signal_value,
                "signal_source": signal_source,
            }, state
        state.baseline_mean = state.ewma_value or signal_value
        state.baseline_std = 0.15

    # Update EWMA
    state.ewma_value = update_ewma(state.ewma_value, signal_value, ewma_alpha)

    # Update CUSUM
    state.cusum_pos, state.cusum_neg = update_cusum(
        cusum_pos=state.cusum_pos,
        cusum_neg=state.cusum_neg,
        observation=signal_value,
        mean=state.baseline_mean,
        std=state.baseline_std or 0.1,
        k=cusum_slack,
    )

    # Compute score
    score = compute_distributional_score(
        cusum_pos=state.cusum_pos,
        cusum_neg=state.cusum_neg,
        ewma_value=state.ewma_value or signal_value,
        baseline_mean=state.baseline_mean,
        cusum_threshold=cusum_threshold,
    )

    cusum_alarm = max(state.cusum_pos, state.cusum_neg) >= cusum_threshold

    logger.debug(
        "distributional_analysis",
        signal_value=signal_value,
        cusum_pos=state.cusum_pos,
        cusum_neg=state.cusum_neg,
        ewma=state.ewma_value,
        score=score,
        alarm=cusum_alarm,
    )

    detail = {
        "signal_value": float(signal_value),
        "signal_source": signal_source,
        "ewma_value": float(state.ewma_value or signal_value),
        "cusum_pos": float(state.cusum_pos),
        "cusum_neg": float(state.cusum_neg),
        "cusum_alarm": cusum_alarm,
        "baseline_mean": float(state.baseline_mean),
        "baseline_std": float(state.baseline_std or 0.1),
        "sample_count": state.sample_count,
    }

    return float(score), detail, state