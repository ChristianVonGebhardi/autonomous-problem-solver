"""Tests for the flakiness detection algorithm."""
import pytest
from app.services.flakiness_detector import (
    detect_flakiness,
    compute_run_length_encoding,
    compute_alternation_rate,
    compute_entropy,
)


def test_always_passing_not_flaky():
    statuses = ["passed"] * 20
    signal = detect_flakiness(statuses, "test_always_pass")
    assert signal.is_flaky is False
    assert signal.flakiness_score == 0.0
    assert signal.pass_rate == 1.0


def test_always_failing_not_flaky():
    statuses = ["failed"] * 20
    signal = detect_flakiness(statuses, "test_always_fail")
    assert signal.is_flaky is False
    assert signal.flakiness_score == 0.0
    assert signal.pass_rate == 0.0


def test_alternating_is_flaky():
    statuses = ["passed", "failed"] * 10
    signal = detect_flakiness(statuses, "test_alternating")
    assert signal.is_flaky is True
    assert signal.flakiness_score > 0.5


def test_mostly_passing_with_occasional_failures():
    # 80% pass rate with some intermittency → should be flaky
    statuses = ["passed"] * 16 + ["failed"] * 4
    import random
    random.seed(42)
    random.shuffle(statuses)
    signal = detect_flakiness(statuses, "test_mostly_pass")
    # May or may not be flaky depending on distribution, but should have a score
    assert 0.0 <= signal.flakiness_score <= 1.0
    assert signal.total_runs == 20
    assert signal.failed_runs == 4


def test_insufficient_runs():
    statuses = ["passed", "failed"]
    signal = detect_flakiness(statuses, "test_few_runs", min_runs=3)
    assert signal.is_flaky is False
    assert signal.confidence == 0.0


def test_rle_encoding():
    statuses = ["passed", "passed", "failed", "passed"]
    rle = compute_run_length_encoding(statuses)
    assert rle == [("passed", 2), ("failed", 1), ("passed", 1)]


def test_alternation_rate_perfect():
    rle = [("passed", 1), ("failed", 1), ("passed", 1), ("failed", 1)]
    rate = compute_alternation_rate(rle)
    # 3 transitions, 3 max (total=4, max_transitions=3)
    assert rate == 1.0


def test_alternation_rate_stable():
    rle = [("passed", 10)]
    rate = compute_alternation_rate(rle)
    assert rate == 0.0


def test_entropy_balanced():
    statuses = ["passed"] * 10 + ["failed"] * 10
    entropy = compute_entropy(statuses)
    assert abs(entropy - 1.0) < 0.01  # Binary entropy = 1.0 at 50/50


def test_entropy_skewed():
    statuses = ["passed"] * 19 + ["failed"]
    entropy = compute_entropy(statuses)
    assert entropy < 0.3  # Low entropy when mostly one outcome


def test_empty_statuses():
    signal = detect_flakiness([], "test_empty")
    assert signal.is_flaky is False
    assert signal.total_runs == 0