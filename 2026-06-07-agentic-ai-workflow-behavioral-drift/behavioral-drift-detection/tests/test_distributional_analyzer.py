"""Tests for the CUSUM/EWMA distributional drift analyzer."""

import pytest
from workers.distributional_analyzer import (
    CusumState,
    update_ewma,
    update_cusum,
    compute_distributional_score,
    analyze_distributional_drift,
)


class TestEWMA:
    def test_first_observation_initializes(self):
        result = update_ewma(None, 0.9, alpha=0.3)
        assert result == 0.9

    def test_smoothing(self):
        result = update_ewma(0.8, 0.9, alpha=0.3)
        expected = 0.3 * 0.9 + 0.7 * 0.8
        assert abs(result - expected) < 1e-10

    def test_high_alpha_more_reactive(self):
        result_high = update_ewma(0.5, 1.0, alpha=0.9)
        result_low = update_ewma(0.5, 1.0, alpha=0.1)
        assert result_high > result_low

    def test_convergence(self):
        """EWMA should converge to a constant signal."""
        value = 0.0
        for _ in range(50):
            value = update_ewma(value, 0.9, alpha=0.3)
        assert abs(value - 0.9) < 0.01


class TestCUSUM:
    def test_no_drift_no_accumulation(self):
        """Observations at mean should not accumulate CUSUM."""
        pos, neg = 0.0, 0.0
        for _ in range(10):
            pos, neg = update_cusum(pos, neg, observation=0.9, mean=0.9, std=0.1, k=0.5)
        # Should stay near 0 with slack
        assert pos < 1.0
        assert neg < 1.0

    def test_upward_shift_detected(self):
        """Sustained upward shift should accumulate positive CUSUM."""
        pos, neg = 0.0, 0.0
        for _ in range(10):
            pos, neg = update_cusum(pos, neg, observation=1.5, mean=0.9, std=0.1, k=0.5)
        assert pos > 5.0  # Should cross threshold of 5

    def test_downward_shift_detected(self):
        """Sustained downward shift should accumulate negative CUSUM."""
        pos, neg = 0.0, 0.0
        for _ in range(10):
            pos, neg = update_cusum(pos, neg, observation=0.3, mean=0.9, std=0.1, k=0.5)
        assert neg > 5.0

    def test_resets_naturally(self):
        """CUSUM accumulation should stop when deviation returns to baseline."""
        pos, neg = 10.0, 0.0  # Start with high accumulation
        pos, neg = update_cusum(pos, neg, observation=0.9, mean=0.9, std=0.1, k=0.5)
        # pos should decrease (clamped at 0)
        assert pos < 10.0


class TestAnalyzeDistributionalDrift:
    def _make_steps(self, confidence: float, n: int = 1) -> list[dict]:
        return [{"confidence": confidence} for _ in range(n)]

    def test_bootstrapping_phase(self):
        """First few samples should score 0 while baseline is established."""
        state = CusumState()
        score, detail, _ = analyze_distributional_drift(
            self._make_steps(0.9),
            state,
        )
        assert score == 0.0
        assert detail.get("reason") == "bootstrapping_baseline"

    def test_stable_signals_low_drift(self):
        """Consistent confidence scores near baseline should yield low drift."""
        state = CusumState(
            baseline_mean=0.9,
            baseline_std=0.05,
            sample_count=10,
            ewma_value=0.9,
        )
        score, _, _ = analyze_distributional_drift(
            self._make_steps(0.9),
            state,
            ewma_alpha=0.3,
            cusum_threshold=5.0,
            cusum_slack=0.5,
        )
        assert score < 0.3

    def test_sustained_drop_triggers_alert(self):
        """Repeated low-confidence observations should accumulate CUSUM."""
        state = CusumState(
            baseline_mean=0.9,
            baseline_std=0.05,
            sample_count=10,
            ewma_value=0.9,
        )
        for _ in range(15):
            score, _, state = analyze_distributional_drift(
                self._make_steps(0.3),  # Way below baseline
                state,
                cusum_threshold=5.0,
                cusum_slack=0.5,
            )
        assert score > 0.5

    def test_no_confidence_falls_back_to_step_count(self):
        """Steps without confidence scores should use step count as signal."""
        state = CusumState(
            baseline_mean=3.0,
            baseline_std=0.5,
            sample_count=10,
            ewma_value=3.0,
        )
        steps = [{"tool_name": "search"}, {"tool_name": "respond"}, {"tool_name": "classify"}]
        score, detail, _ = analyze_distributional_drift(steps, state)
        assert detail["signal_source"] == "step_count"
        assert detail["signal_value"] == 3.0