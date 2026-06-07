"""Tests for the structural drift analyzer."""

import pytest
from workers.structural_analyzer import (
    levenshtein_distance,
    normalized_edit_distance,
    analyze_structural_drift,
)


class TestLevenshteinDistance:
    def test_identical_sequences(self):
        assert levenshtein_distance(["a", "b", "c"], ["a", "b", "c"]) == 0

    def test_empty_sequences(self):
        assert levenshtein_distance([], []) == 0

    def test_one_empty(self):
        assert levenshtein_distance(["a", "b"], []) == 2
        assert levenshtein_distance([], ["a", "b"]) == 2

    def test_single_insertion(self):
        assert levenshtein_distance(["a", "b"], ["a", "x", "b"]) == 1

    def test_single_deletion(self):
        assert levenshtein_distance(["a", "x", "b"], ["a", "b"]) == 1

    def test_single_substitution(self):
        assert levenshtein_distance(["a", "b"], ["a", "c"]) == 1

    def test_completely_different(self):
        assert levenshtein_distance(["a", "b", "c"], ["x", "y", "z"]) == 3


class TestNormalizedEditDistance:
    def test_identical(self):
        assert normalized_edit_distance(["a", "b"], ["a", "b"]) == 0.0

    def test_both_empty(self):
        assert normalized_edit_distance([], []) == 0.0

    def test_completely_different(self):
        result = normalized_edit_distance(["a", "b", "c"], ["x", "y", "z"])
        assert result == 1.0

    def test_half_different(self):
        result = normalized_edit_distance(["a", "b"], ["a", "c"])
        assert result == 0.5


class TestAnalyzeStructuralDrift:
    def test_no_baselines(self):
        result = analyze_structural_drift(["search", "respond"], [])
        assert result["score"] == 0.0
        assert result["detail"]["reason"] == "no_baselines"

    def test_identical_to_baseline(self):
        baseline = ["search", "retrieve", "respond"]
        result = analyze_structural_drift(baseline, [baseline])
        assert result["score"] == 0.0

    def test_completely_different_sequence(self):
        result = analyze_structural_drift(
            ["tool_x", "tool_y"],
            [["search", "retrieve", "classify", "respond"]],
        )
        assert result["score"] > 0.3

    def test_unexpected_tools(self):
        result = analyze_structural_drift(
            ["search", "hack", "respond"],
            [["search", "respond"]],
            expected_tools=["search", "respond"],
        )
        assert "hack" in result["detail"]["unexpected_tools"]
        assert result["score"] > 0.0

    def test_missing_tools(self):
        result = analyze_structural_drift(
            ["search"],
            [["search", "retrieve", "respond"]],
            expected_tools=["search", "retrieve", "respond"],
        )
        assert result["score"] > 0.0

    def test_score_range(self):
        """Score must always be in [0, 1]."""
        result = analyze_structural_drift(
            ["a", "b", "c", "d", "e"],
            [["x"], ["y", "z"]],
            expected_tools=["p", "q"],
        )
        assert 0.0 <= result["score"] <= 1.0