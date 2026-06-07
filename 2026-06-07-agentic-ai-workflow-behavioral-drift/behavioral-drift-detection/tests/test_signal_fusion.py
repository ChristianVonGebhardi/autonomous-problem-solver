"""Tests for the signal fusion layer."""

import pytest
from workers.signal_fusion import fuse_signals, classify_severity


class TestClassifySeverity:
    def test_low(self):
        assert classify_severity(0.1, threshold=0.65) == "low"

    def test_medium(self):
        assert classify_severity(0.5, threshold=0.65) == "medium"

    def test_high(self):
        assert classify_severity(0.7, threshold=0.65) == "high"

    def test_critical(self):
        assert classify_severity(0.95, threshold=0.65) == "critical"


class TestFuseSignals:
    def test_all_zero_no_alert(self):
        result = fuse_signals(0.0, 0.0, 0.0)
        assert result["composite_score"] == 0.0
        assert result["alert_triggered"] == False
        assert result["severity"] == "low"

    def test_all_one_critical(self):
        result = fuse_signals(1.0, 1.0, 1.0)
        assert result["composite_score"] == 1.0
        assert result["alert_triggered"] == True
        assert result["severity"] == "critical"

    def test_weighted_composite(self):
        result = fuse_signals(
            structural_score=1.0,
            semantic_score=0.0,
            distributional_score=0.0,
            structural_weight=0.5,
            semantic_weight=0.3,
            distributional_weight=0.2,
        )
        assert abs(result["composite_score"] - 0.5) < 0.01

    def test_alert_at_threshold(self):
        result = fuse_signals(1.0, 1.0, 1.0, alert_threshold=0.5)
        assert result["alert_triggered"] == True

    def test_no_alert_below_threshold(self):
        result = fuse_signals(0.1, 0.1, 0.1, alert_threshold=0.9)
        assert result["alert_triggered"] == False

    def test_score_always_in_range(self):
        """Composite score must always be in [0, 1]."""
        for s, e, d in [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.5, 0.7, 0.3)]:
            result = fuse_signals(s, e, d)
            assert 0.0 <= result["composite_score"] <= 1.0

    def test_weights_normalized(self):
        """Weights that don't sum to 1 should be normalized."""
        result = fuse_signals(
            0.5, 0.5, 0.5,
            structural_weight=2.0,
            semantic_weight=2.0,
            distributional_weight=2.0,
        )
        # Should produce same as equal weights
        expected = fuse_signals(0.5, 0.5, 0.5)
        assert abs(result["composite_score"] - expected["composite_score"]) < 0.01