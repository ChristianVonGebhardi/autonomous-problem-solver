"""
Structural Drift Analyzer

Detects changes in:
- Tool selection sequences (which tools are called)
- Step ordering (are steps executed in the expected order)
- Step count (missing or added steps)

Uses Levenshtein-style edit distance on tool/step sequences compared
against the baseline distribution.
"""

import logging
from typing import List, Optional, Dict, Any
from collections import Counter
import math

logger = logging.getLogger(__name__)


def _sequence_edit_distance(seq_a: List[str], seq_b: List[str]) -> int:
    """
    Compute Levenshtein edit distance between two sequences.
    Used for tool sequence comparison.
    """
    if not seq_a and not seq_b:
        return 0
    if not seq_a:
        return len(seq_b)
    if not seq_b:
        return len(seq_a)

    # DP table
    dp = list(range(len(seq_b) + 1))
    for i, ca in enumerate(seq_a):
        new_dp = [i + 1]
        for j, cb in enumerate(seq_b):
            if ca == cb:
                new_dp.append(dp[j])
            else:
                new_dp.append(1 + min(dp[j], dp[j + 1], new_dp[-1]))
        dp = new_dp

    return dp[-1]


def _normalized_edit_distance(seq_a: List[str], seq_b: List[str]) -> float:
    """Edit distance normalized to [0, 1]."""
    if not seq_a and not seq_b:
        return 0.0
    max_len = max(len(seq_a), len(seq_b), 1)
    return _sequence_edit_distance(seq_a, seq_b) / max_len


def _jaccard_distance(set_a: set, set_b: set) -> float:
    """1 - Jaccard similarity for set-based comparison."""
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    intersection = set_a & set_b
    return 1.0 - len(intersection) / len(union)


def compute_structural_score(
    current_tool_sequence: List[Optional[str]],
    current_step_sequence: List[str],
    baseline_tool_sequences: List[List[Optional[str]]],
    baseline_step_sequences: List[List[str]],
) -> Dict[str, Any]:
    """
    Compute structural drift score for a run against baselines.

    Returns:
        dict with:
          - score: float [0, 1] where 0 = no drift, 1 = maximum drift
          - tool_sequence_distance: normalized edit distance for tools
          - step_sequence_distance: normalized edit distance for steps
          - tool_set_drift: Jaccard distance for tool vocabulary
          - step_count_drift: normalized step count difference
          - details: detailed breakdown
    """
    if not baseline_tool_sequences:
        # No baselines yet — cannot score
        return {
            "score": 0.0,
            "tool_sequence_distance": 0.0,
            "step_sequence_distance": 0.0,
            "tool_set_drift": 0.0,
            "step_count_drift": 0.0,
            "baseline_count": 0,
            "details": {"note": "No baselines available"},
        }

    # Clean up None values in tool sequences
    clean_current_tools = [t for t in current_tool_sequence if t is not None]
    clean_baselines_tools = [
        [t for t in seq if t is not None] for seq in baseline_tool_sequences
    ]

    # 1. Tool sequence distance — compare against each baseline, take minimum
    #    (closest baseline match), then average the bottom-half distances
    tool_seq_distances = [
        _normalized_edit_distance(clean_current_tools, b)
        for b in clean_baselines_tools
    ]
    # Use median distance as the representative score
    tool_seq_distances_sorted = sorted(tool_seq_distances)
    median_idx = len(tool_seq_distances_sorted) // 2
    tool_seq_drift = tool_seq_distances_sorted[median_idx]

    # 2. Step sequence distance
    step_seq_distances = [
        _normalized_edit_distance(current_step_sequence, b)
        for b in baseline_step_sequences
    ]
    step_seq_distances_sorted = sorted(step_seq_distances)
    median_idx = len(step_seq_distances_sorted) // 2
    step_seq_drift = step_seq_distances_sorted[median_idx]

    # 3. Tool vocabulary drift (which tools appear at all)
    current_tool_set = set(clean_current_tools)
    baseline_tool_sets = [set(b) for b in clean_baselines_tools]
    # Union of all baseline tool sets = expected vocabulary
    baseline_vocab = set().union(*baseline_tool_sets)
    tool_vocab_drift = _jaccard_distance(current_tool_set, baseline_vocab)

    # 4. Step count drift
    baseline_step_counts = [len(seq) for seq in baseline_step_sequences]
    if baseline_step_counts:
        avg_baseline_steps = sum(baseline_step_counts) / len(baseline_step_counts)
        step_count_drift = abs(len(current_step_sequence) - avg_baseline_steps) / max(
            avg_baseline_steps, 1
        )
        step_count_drift = min(step_count_drift, 1.0)
    else:
        step_count_drift = 0.0

    # Composite structural score — weighted average
    composite = (
        0.40 * tool_seq_drift
        + 0.35 * step_seq_drift
        + 0.15 * tool_vocab_drift
        + 0.10 * step_count_drift
    )

    return {
        "score": round(min(composite, 1.0), 4),
        "tool_sequence_distance": round(tool_seq_drift, 4),
        "step_sequence_distance": round(step_seq_drift, 4),
        "tool_set_drift": round(tool_vocab_drift, 4),
        "step_count_drift": round(step_count_drift, 4),
        "baseline_count": len(baseline_tool_sequences),
        "current_tools": clean_current_tools,
        "baseline_tool_counts": Counter(
            t for seq in clean_baselines_tools for t in seq
        ),
    }