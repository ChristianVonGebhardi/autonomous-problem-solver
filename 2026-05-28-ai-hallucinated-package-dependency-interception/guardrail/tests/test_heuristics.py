"""Tests for the heuristic analysis engine."""
import pytest
from core.heuristics import HeuristicEngine
from core.models import HeuristicResult


@pytest.fixture
def engine():
    return HeuristicEngine()


class TestEditDistance:
    def test_exact_match_scores_zero(self, engine):
        result = engine.analyze("requests", "pypi")
        # exact match should have near-zero edit distance score
        assert result.edit_distance == 0
        assert result.score < 0.3

    def test_one_char_typo_is_suspicious(self, engine):
        # "reqeusts" is 1 edit from "requests"
        result = engine.analyze("reqeusts", "pypi")
        assert result.edit_distance is not None
        assert result.edit_distance <= 2
        assert result.score > 0.3

    def test_two_char_typo_detected(self, engine):
        # "numppy" is 1 edit from "numpy"
        result = engine.analyze("numppy", "pypi")
        assert result.score > 0.3
        assert len(result.similar_packages) > 0

    def test_legitimate_package_is_clean(self, engine):
        result = engine.analyze("fastapi", "pypi")
        assert result.edit_distance == 0
        assert result.score < 0.1

    def test_similar_packages_populated(self, engine):
        result = engine.analyze("reqests", "pypi")  # missing 'u'
        assert len(result.similar_packages) > 0
        assert any("request" in p for p in result.similar_packages)


class TestAIPatterns:
    def test_overly_hyphenated_flagged(self, engine):
        result = engine.analyze("some-very-long-package-name", "pypi")
        flags = result.flags
        assert any("hyphenated" in f or "pattern" in f for f in flags) or result.score > 0.1

    def test_known_package_suffix_flagged(self, engine):
        result = engine.analyze("numpy-utils", "pypi")
        assert any("known-package-suffix" in f or "similar" in f for f in result.flags)

    def test_ai_prefix_pattern(self, engine):
        result = engine.analyze("ai-utils", "pypi")
        assert any("ai-prefix" in f for f in result.flags) or result.score > 0.1

    def test_generic_suffix_flagged(self, engine):
        result = engine.analyze("mypackage-wrapper", "pypi")
        assert any("suffix" in f for f in result.flags) or result.score > 0.0

    def test_valid_package_no_false_positive(self, engine):
        result = engine.analyze("click", "pypi")
        assert result.score < 0.5

    def test_mixed_separators_flagged(self, engine):
        result = engine.analyze("my-package_name", "pypi")
        assert any("mixed-separator" in f for f in result.flags)


class TestStructural:
    def test_invalid_pypi_name(self, engine):
        result = engine.analyze("my package!", "pypi")
        assert any("invalid-pypi" in f for f in result.flags)

    def test_valid_npm_scoped_package(self, engine):
        result = engine.analyze("@scope/package", "npm")
        # Should not flag valid scoped packages
        structural_flags = [f for f in result.flags if "invalid-npm" in f]
        assert len(structural_flags) == 0

    def test_camelcase_flagged(self, engine):
        result = engine.analyze("myPackageName", "pypi")
        assert any("camel" in f for f in result.flags) or result.score > 0.1


class TestCombinedScores:
    def test_hallucinated_package_high_score(self, engine):
        # A made-up name that doesn't resemble anything real
        result = engine.analyze("numpy-ai-helper-toolkit", "pypi")
        assert result.score > 0.2  # Should have some flags

    def test_obvious_typosquat_high_score(self, engine):
        result = engine.analyze("reqests", "pypi")
        assert result.score > 0.4

    def test_npm_package_ecosystem_check(self, engine):
        result = engine.analyze("lodsh", "npm")  # close to "lodash"
        assert result.score > 0.3

    def test_cargo_package_check(self, engine):
        result = engine.analyze("serde_json", "cargo")
        assert result.edit_distance == 0
        assert result.score < 0.2