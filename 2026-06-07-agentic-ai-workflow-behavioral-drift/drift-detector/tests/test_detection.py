"""
Tests for drift detection algorithms.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.detection.structural import (
    compute_structural_score,
    _normalized_edit_distance,
    _jaccard_distance,
)
from backend.detection.semantic import compute_semantic_score, cosine_distance
from backend.detection.distributional import (
    compute_distributional_score,
    CUSUMDetector,
    EWMADetector,
)
from backend.detection.fusion import (
    compute_composite_score,
    classify_alert_level,
    fuse_drift_signals,
)


# ── Structural Tests ──────────────────────────────────────────────────────────

class TestStructuralDetector:
    def test_identical_sequences_zero_drift(self):
        result = compute_structural_score(
            current_tool_sequence=["search", "lookup", "respond"],
            current_step_sequence=["step1", "step2", "step3"],
            baseline_tool_sequences=[["search", "lookup", "respond"]],
            baseline_step_sequences=[["step1", "step2", "step3"]],
        )
        assert result["score"] == 0.0
        assert result["tool_sequence_distance"] == 0.0

    def test_completely_different_tools_high_drift(self):
        result = compute_structural_score(
            current_tool_sequence=["web_search", "scrape", "summarize"],
            current_step_sequence=["step_a", "step_b", "step_c"],
            baseline_tool_sequences=[["search_kb", "lookup_customer", "respond"]],
            baseline_step_sequences=[["classify", "retrieve", "generate"]],
        )
        assert result["score"] > 0.5

    def test_no_baselines_returns_zero(self):
        result = compute_structural_score(
            current_tool_sequence=["tool1"],
            current_step_sequence=["step1"],
            baseline_tool_sequences=[],
            baseline_step_sequences=[],
        )
        assert result["score"] == 0.0
        assert result["baseline_count"] == 0

    def test_edit_distance_identical(self):
        assert _normalized_edit_distance(["a", "b", "c"], ["a", "b", "c"]) == 0.0

    def test_edit_distance_completely_different(self):
        dist = _normalized_edit_distance(["a", "b", "c"], ["x", "y", "z"])
        assert dist > 0.0

    def test_edit_distance_empty_vs_nonempty(self):
        dist = _normalized_edit_distance([], ["a", "b"])
        assert dist == 1.0

    def test_jaccard_distance_identical_sets(self):
        assert _jaccard_distance({"a", "b"}, {"a", "b"}) == 0.0

    def test_jaccard_distance_disjoint_sets(self):
        assert _jaccard_distance({"a", "b"}, {"c", "d"}) == 1.0

    def test_partial_overlap(self):
        result = compute_structural_score(
            current_tool_sequence=["search", "web_lookup", "respond"],
            current_step_sequence=["step1", "step2", "step3"],
            baseline_tool_sequences=[["search", "lookup", "respond"]],
            baseline_step_sequences=[["step1", "step2", "step3"]],
        )
        # Some drift but not maximum
        assert 0.0 < result["score"] < 1.0


# ── Semantic Tests ────────────────────────────────────────────────────────────

class TestSemanticDetector:
    def test_no_baselines_zero_drift(self):
        result = compute_semantic_score(
            run_embedding=[0.1, 0.2, 0.3],
            baseline_embeddings=[],
        )
        assert result["score"] == 0.0

    def test_no_run_embedding_zero_drift(self):
        result = compute_semantic_score(
            run_embedding=None,
            baseline_embeddings=[[0.1, 0.2, 0.3]],
        )
        assert result["score"] == 0.0

    def test_identical_to_baseline_zero_drift(self):
        baseline = [1.0, 0.0, 0.0]
        result = compute_semantic_score(
            run_embedding=baseline,
            baseline_embeddings=[baseline, baseline],
        )
        assert result["score"] == 0.0

    def test_orthogonal_vector_high_drift(self):
        # Baseline points in x-direction, current points in y-direction
        import math
        baseline_embs = [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]]
        current = [0.0, 1.0, 0.0]
        result = compute_semantic_score(
            run_embedding=current,
            baseline_embeddings=baseline_embs,
        )
        # Cosine distance should be high (~1.0)
        assert result["distance_to_centroid"] > 0.8

    def test_cosine_distance_range(self):
        dist = cosine_distance([1.0, 0.0], [0.0, 1.0])
        assert 0.9 < dist <= 1.1  # Should be ~1.0 for orthogonal vectors


# ── Distributional Tests ──────────────────────────────────────────────────────

class TestDistributionalDetector:
    def test_cusum_stable_signal(self):
        detector = CUSUMDetector(k=0.5, h=5.0)
        # Feed stable values at target
        for _ in range(20):
            cusum_val, alarm = detector.update(1.0, target=1.0, sigma=0.1)
        assert not alarm
        assert detector.normalized_score < 0.5

    def test_cusum_detects_shift(self):
        detector = CUSUMDetector(k=0.5, h=5.0)
        # Feed values significantly above target
        for _ in range(15):
            cusum_val, alarm = detector.update(3.0, target=1.0, sigma=0.5)
        assert alarm  # Should have triggered

    def test_ewma_stable(self):
        detector = EWMADetector(lambda_=0.3, l_sigma=3.0)
        _, alarm = detector.update(1.0, target=1.0, sigma=0.1)
        assert not alarm

    def test_distributional_no_data_zero_score(self):
        result = compute_distributional_score(
            current_confidence=0.8,
            current_token_count=None,
            current_latency_ms=None,
            baseline_confidences=[],
            baseline_token_counts=[],
            recent_confidences=[],
            recent_token_counts=[],
        )
        assert result["score"] == 0.0

    def test_distributional_stable_confidence(self):
        baseline = [0.85, 0.87, 0.83, 0.86, 0.84]
        recent = [0.85, 0.86, 0.84, 0.85, 0.86]
        result = compute_distributional_score(
            current_confidence=0.85,
            current_token_count=None,
            current_latency_ms=None,
            baseline_confidences=baseline,
            baseline_token_counts=[],
            recent_confidences=recent,
            recent_token_counts=[],
        )
        assert result["score"] < 0.3  # Low drift for stable signal

    def test_distributional_detects_confidence_drop(self):
        baseline = [0.85, 0.87, 0.83, 0.86, 0.84]
        recent = [0.6, 0.55, 0.5, 0.48, 0.45]  # Declining confidence
        result = compute_distributional_score(
            current_confidence=0.42,  # Well below baseline
            current_token_count=None,
            current_latency_ms=None,
            baseline_confidences=baseline,
            baseline_token_counts=[],
            recent_confidences=recent,
            recent_token_counts=[],
        )
        assert result["score"] > 0.2  # Should detect the shift


# ── Fusion Tests ──────────────────────────────────────────────────────────────

class TestFusion:
    def test_zero_scores_normal(self):
        assert classify_alert_level(0.0) == "normal"

    def test_mid_score_warning(self):
        assert classify_alert_level(0.50) == "warning"

    def test_high_score_alert(self):
        assert classify_alert_level(0.75) == "alert"

    def test_composite_weights(self):
        score = compute_composite_score(
            structural_score=0.0,
            semantic_score=0.0,
            distributional_score=0.0,
        )
        assert score == 0.0

        score = compute_composite_score(
            structural_score=1.0,
            semantic_score=1.0,
            distributional_score=1.0,
        )
        assert score == 1.0

    def test_fuse_returns_drift_result(self):
        result = fuse_drift_signals(
            workflow_id="test-wf",
            run_id="run-123",
            structural_result={"score": 0.8},
            semantic_result={"score": 0.7},
            distributional_result={"score": 0.6},
        )
        assert result.workflow_id == "test-wf"
        assert result.run_id == "run-123"
        assert 0.6 < result.composite_score <= 1.0
        assert result.alert_level == "alert"

    def test_fuse_low_scores_normal(self):
        result = fuse_drift_signals(
            workflow_id="test-wf",
            run_id="run-456",
            structural_result={"score": 0.1},
            semantic_result={"score": 0.05},
            distributional_result={"score": 0.08},
        )
        assert result.alert_level == "normal"
        assert result.composite_score < 0.4