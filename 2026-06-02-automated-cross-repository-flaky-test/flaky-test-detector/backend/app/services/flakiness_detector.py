"""
Statistical flakiness detection using run-length encoding and pass/fail ratio analysis.
Implements KS-test style distribution comparison to identify non-deterministic tests.
"""
import math
from typing import List, Tuple, Optional
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class FlakinesSignal:
    test_name: str
    flakiness_score: float  # 0-1
    confidence: float       # 0-1
    total_runs: int
    failed_runs: int
    pass_rate: float
    is_flaky: bool
    rle_pattern: List[Tuple[str, int]]  # run-length encoded status sequence
    alternation_rate: float  # how often status changes
    longest_run: int        # longest consecutive same-status run


def compute_run_length_encoding(statuses: List[str]) -> List[Tuple[str, int]]:
    """Encode a sequence of statuses as run-length pairs [(status, count), ...]."""
    if not statuses:
        return []
    
    rle = []
    current = statuses[0]
    count = 1
    
    for status in statuses[1:]:
        if status == current:
            count += 1
        else:
            rle.append((current, count))
            current = status
            count = 1
    rle.append((current, count))
    return rle


def compute_alternation_rate(rle: List[Tuple[str, int]]) -> float:
    """
    Alternation rate: proportion of transitions relative to max possible transitions.
    A perfectly alternating sequence [P,F,P,F,...] has rate 1.0.
    A stable sequence [P,P,P,...] has rate 0.0.
    """
    if len(rle) <= 1:
        return 0.0
    transitions = len(rle) - 1
    total = sum(count for _, count in rle)
    max_transitions = total - 1
    return transitions / max_transitions if max_transitions > 0 else 0.0


def compute_entropy(statuses: List[str]) -> float:
    """Binary entropy of the pass/fail distribution."""
    if not statuses:
        return 0.0
    n = len(statuses)
    failures = sum(1 for s in statuses if s != "passed")
    p_fail = failures / n
    p_pass = 1 - p_fail
    if p_fail == 0 or p_pass == 0:
        return 0.0
    return -(p_fail * math.log2(p_fail) + p_pass * math.log2(p_pass))


def ks_statistic(statuses: List[str], window: int = 5) -> float:
    """
    Simplified KS-style statistic: compare pass/fail distributions in windows.
    Returns the maximum difference between windowed CDFs.
    """
    if len(statuses) < window * 2:
        return 0.0
    
    mid = len(statuses) // 2
    first_half = statuses[:mid]
    second_half = statuses[mid:]
    
    def pass_rate(seq):
        return sum(1 for s in seq if s == "passed") / len(seq) if seq else 0
    
    return abs(pass_rate(first_half) - pass_rate(second_half))


def detect_flakiness(
    statuses: List[str],
    test_name: str,
    min_runs: int = 3,
    flakiness_threshold: float = 0.3,
) -> FlakinesSignal:
    """
    Main flakiness detection algorithm.
    
    Combines:
    1. Pass rate (must be between 0 and 1, not always one value)
    2. Alternation rate (how often the result changes)
    3. Distribution entropy (randomness of outcomes)
    4. KS statistic (consistency across time windows)
    """
    if not statuses:
        return FlakinesSignal(
            test_name=test_name,
            flakiness_score=0.0,
            confidence=0.0,
            total_runs=0,
            failed_runs=0,
            pass_rate=1.0,
            is_flaky=False,
            rle_pattern=[],
            alternation_rate=0.0,
            longest_run=0,
        )

    total = len(statuses)
    failed = sum(1 for s in statuses if s != "passed")
    pass_rate = 1.0 - (failed / total)

    rle = compute_run_length_encoding(statuses)
    alternation_rate = compute_alternation_rate(rle)
    entropy = compute_entropy(statuses)
    ks_stat = ks_statistic(statuses)
    longest_run = max(count for _, count in rle) if rle else 0

    # Tests that always pass or always fail are NOT flaky
    if pass_rate == 1.0 or pass_rate == 0.0:
        return FlakinesSignal(
            test_name=test_name,
            flakiness_score=0.0,
            confidence=1.0 if total >= min_runs else 0.5,
            total_runs=total,
            failed_runs=failed,
            pass_rate=pass_rate,
            is_flaky=False,
            rle_pattern=rle,
            alternation_rate=alternation_rate,
            longest_run=longest_run,
        )

    # Flakiness score: weighted combination of signals
    # - High alternation = more flaky
    # - High entropy = more random = more flaky  
    # - High KS stat = distribution shifted over time = more flaky
    # - Pass rate near 0.5 = maximally uncertain
    pass_rate_uncertainty = 1.0 - abs(2 * pass_rate - 1)  # peaks at 0.5 pass rate

    flakiness_score = (
        0.35 * alternation_rate +
        0.25 * entropy +           # max 1.0
        0.20 * ks_stat +           # max 1.0
        0.20 * pass_rate_uncertainty
    )

    # Confidence scales with number of runs
    confidence = min(1.0, (total - min_runs + 1) / 10.0) if total >= min_runs else 0.0
    confidence = max(0.0, confidence)

    is_flaky = flakiness_score >= flakiness_threshold and total >= min_runs

    logger.debug(
        "flakiness_detection",
        test=test_name,
        total=total,
        pass_rate=pass_rate,
        alternation=alternation_rate,
        entropy=entropy,
        ks_stat=ks_stat,
        score=flakiness_score,
        is_flaky=is_flaky,
    )

    return FlakinesSignal(
        test_name=test_name,
        flakiness_score=min(1.0, flakiness_score),
        confidence=confidence,
        total_runs=total,
        failed_runs=failed,
        pass_rate=pass_rate,
        is_flaky=is_flaky,
        rle_pattern=rle,
        alternation_rate=alternation_rate,
        longest_run=longest_run,
    )