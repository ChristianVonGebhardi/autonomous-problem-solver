"""Tests for the semantic drift analyzer."""

from __future__ import annotations

import math
import pytest

from workers.embeddings import (
    cosine_distance,
    aggregate_run_embedding,
    mean_cosine_distance_to_baselines,
)
from workers.semantic_analyzer import analyze_semantic_drift, _extract_step_outputs


class TestCosineDistance:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_distance(v, v) == pytest.approx(0.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_distance(a, b) == pytest.approx(1.0, abs=1e-6)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        # distance = 1 - (-1) = 2, clipped to 1.0
        assert cosine_distance(a, b) == pytest.approx(1.0, abs=1e-6)

    def test_zero_vector_returns_1(self):
        assert cosine_distance([0.0, 0.0], [1.0, 0.0]) == 1.0

    def test_result_in_range(self):
        import random
        random.seed(42)
        for _ in range(20):
            a = [random.gauss(0, 1) for _ in range(10)]
            b = [random.gauss(0, 1) for _ in range(10)]
            d = cosine_distance(a, b)
            assert 0.0 <= d <= 1.0


class TestExtractStepOutputs:
    def test_extracts_non_empty(self):
        steps = [
            {"output_text": "hello world"},
            {"output_text": ""},
            {"output_text": None},
            {"output_text": "  foo  "},
        ]
        result = _extract_step_outputs(steps)
        assert result == ["hello world", "foo"]

    def test_missing_key(self):
        steps = [{"tool_name": "search"}, {"output_text": "result"}]
        result = _extract_step_outputs(steps)
        assert result == ["result"]

    def test_empty_steps(self):
        assert _extract_step_outputs([]) == []


class TestAggregateRunEmbedding:
    def test_returns_list_of_floats(self):
        result = aggregate_run_embedding(["hello world", "test output"])
        assert result is not None
        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)

    def test_normalized(self):
        import math
        result = aggregate_run_embedding(["some text here"])
        assert result is not None
        norm = math.sqrt(sum(x * x for x in result))
        assert norm == pytest.approx(1.0, abs=1e-5)

    def test_empty_returns_none(self):
        result = aggregate_run_embedding([])
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = aggregate_run_embedding(["   ", "  "])
        assert result is None


class TestMeanCosineDistanceToBaselines:
    def test_no_baselines_returns_zero(self):
        embedding = [1.0, 0.0, 0.0]
        assert mean_cosine_distance_to_baselines(embedding, []) == 0.0

    def test_identical_embedding_distance_zero(self):
        emb = aggregate_run_embedding(["hello world test"])
        assert emb is not None
        dist = mean_cosine_distance_to_baselines(emb, [emb])
        assert dist == pytest.approx(0.0, abs=1e-5)

    def test_uses_nearest_baseline(self):
        """Should return min distance (nearest baseline), not mean."""
        close = aggregate_run_embedding(["The customer has a billing question"])
        far = aggregate_run_embedding(["The rocket launched successfully"])
        query = aggregate_run_embedding(["The customer is inquiring about a bill"])
        assert close and far and query
        dist = mean_cosine_distance_to_baselines(query, [close, far])
        dist_to_close = cosine_distance(query, close)
        assert dist == pytest.approx(dist_to_close, abs=1e-5)


class TestAnalyzeSemanticDrift:
    def test_no_steps_returns_zero(self):
        result = analyze_semantic_drift(run_steps=[], baseline_embeddings=[])
        assert result["score"] == 0.0
        assert result["detail"]["reason"] == "no_output_text"

    def test_no_baselines_returns_zero(self):
        steps = [{"output_text": "some output from the agent"}]
        result = analyze_semantic_drift(run_steps=steps, baseline_embeddings=[])
        assert result["score"] == 0.0
        assert "embedding" in result
        assert result["embedding"] is not None  # still computed for future use

    def test_similar_to_baseline_low_score(self):
        baseline_text = "The customer submitted a billing dispute and we retrieved the relevant policy."
        run_text = "A billing dispute was filed. We looked up the applicable policy document."

        baseline_emb = aggregate_run_embedding([baseline_text])
        assert baseline_emb is not None

        steps = [{"output_text": run_text}]
        result = analyze_semantic_drift(
            run_steps=steps,
            baseline_embeddings=[baseline_emb],
        )
        assert result["score"] < 0.5

    def test_diverged_from_baseline_higher_score(self):
        baseline_text = "The customer submitted a billing dispute and we retrieved the relevant policy."
        run_text = "The Mars rover has successfully landed and begun soil sample collection."

        baseline_emb = aggregate_run_embedding([baseline_text])
        assert baseline_emb is not None

        steps = [{"output_text": run_text}]
        result = analyze_semantic_drift(
            run_steps=steps,
            baseline_embeddings=[baseline_emb],
        )
        # Domain-shifted output should score much higher than same-domain
        assert result["score"] > 0.2

    def test_score_in_range(self):
        baseline_emb = aggregate_run_embedding(["reference text"])
        steps = [{"output_text": "some agent output text here"}]
        result = analyze_semantic_drift(
            run_steps=steps,
            baseline_embeddings=[baseline_emb],
        )
        assert 0.0 <= result["score"] <= 1.0

    def test_detail_contains_expected_keys(self):
        baseline_emb = aggregate_run_embedding(["baseline output"])
        steps = [{"output_text": "run output"}]
        result = analyze_semantic_drift(
            run_steps=steps,
            baseline_embeddings=[baseline_emb],
        )
        assert "min_cosine_distance" in result["detail"]
        assert "step_output_count" in result["detail"]
        assert "baseline_count" in result["detail"]