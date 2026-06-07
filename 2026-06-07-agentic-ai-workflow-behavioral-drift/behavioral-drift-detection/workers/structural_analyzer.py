"""
Structural Drift Analyzer

Detects deviations in:
  1. Tool selection sequence (which tools were called, in what order)
  2. Step count relative to baseline
  3. Missing or unexpected tools vs. workflow's expected_tools
  
Uses edit distance (Levenshtein) on tool sequences to quantify structural deviation.
No ML required — pure algorithmic comparison against baseline tool sequences.
"""

from __future__ import annotations

from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


def levenshtein_distance(seq_a: list[str], seq_b: list[str]) -> int:
    """
    Compute Levenshtein edit distance between two sequences of tool names.
    
    Each insertion, deletion, or substitution counts as 1 edit.
    """
    m, n = len(seq_a), len(seq_b)
    
    # DP table
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    
    return dp[m][n]


def normalized_edit_distance(seq_a: list[str], seq_b: list[str]) -> float:
    """
    Normalized edit distance in [0, 1].
    
    0.0 = identical sequences
    1.0 = completely different (max edits = max(len_a, len_b))
    """
    if not seq_a and not seq_b:
        return 0.0
    
    max_len = max(len(seq_a), len(seq_b))
    if max_len == 0:
        return 0.0
    
    dist = levenshtein_distance(seq_a, seq_b)
    return min(dist / max_len, 1.0)


def analyze_structural_drift(
    run_tool_sequence: list[str],
    baseline_sequences: list[list[str]],
    expected_tools: Optional[list[str]] = None,
) -> dict:
    """
    Compute structural drift score for a run against baseline tool sequences.
    
    Args:
        run_tool_sequence: Tool names called in this run, in order.
        baseline_sequences: List of golden-run tool sequences.
        expected_tools: Optional registered set of expected tool names.
    
    Returns dict with:
        score: float in [0, 1] — 0 is no drift, 1 is maximum drift
        detail: breakdown of contributing factors
    """
    if not baseline_sequences:
        return {
            "score": 0.0,
            "detail": {
                "reason": "no_baselines",
                "min_edit_distance": None,
                "step_count_deviation": None,
                "unexpected_tools": [],
                "missing_tools": [],
            }
        }

    # 1. Edit distance to nearest baseline
    edit_distances = [
        normalized_edit_distance(run_tool_sequence, baseline)
        for baseline in baseline_sequences
    ]
    min_edit_dist = min(edit_distances)
    
    # 2. Step count deviation relative to baseline median
    baseline_lengths = [len(b) for b in baseline_sequences]
    median_length = sorted(baseline_lengths)[len(baseline_lengths) // 2]
    run_length = len(run_tool_sequence)
    
    if median_length > 0:
        length_dev = abs(run_length - median_length) / median_length
    else:
        length_dev = 0.0
    length_dev = min(length_dev, 1.0)
    
    # 3. Unexpected / missing tools
    unexpected_tools = []
    missing_tools = []
    if expected_tools:
        run_tool_set = set(run_tool_sequence)
        expected_set = set(expected_tools)
        unexpected_tools = list(run_tool_set - expected_set)
        missing_tools = list(expected_set - run_tool_set)
    
    unexpected_penalty = min(len(unexpected_tools) * 0.15, 0.45)
    missing_penalty = min(len(missing_tools) * 0.1, 0.3)
    
    # Weighted composite structural score
    # Primary: edit distance (70%), secondary: length deviation (30%)
    base_score = 0.70 * min_edit_dist + 0.30 * length_dev
    
    # Add tool inventory penalties (capped at 0.3 additional)
    score = min(base_score + 0.5 * (unexpected_penalty + missing_penalty), 1.0)

    logger.debug(
        "structural_analysis",
        min_edit_dist=min_edit_dist,
        length_dev=length_dev,
        unexpected_tools=unexpected_tools,
        score=score,
    )

    return {
        "score": float(score),
        "detail": {
            "min_edit_distance": float(min_edit_dist),
            "step_count_deviation": float(length_dev),
            "run_length": run_length,
            "median_baseline_length": median_length,
            "unexpected_tools": unexpected_tools,
            "missing_tools": missing_tools,
            "edit_distances_to_baselines": [float(d) for d in edit_distances],
        }
    }