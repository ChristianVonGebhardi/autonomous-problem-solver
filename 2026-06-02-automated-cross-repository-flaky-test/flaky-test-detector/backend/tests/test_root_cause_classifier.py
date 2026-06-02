"""Tests for the root cause classifier."""
import pytest
from app.services.root_cause_classifier import classify_failure, classify_rule_based


def test_timing_pattern_timeout():
    result = classify_rule_based(
        log_text="TimeoutError: Expected webhook callback within 2000ms but timed out",
        error_message="Timeout after 5200ms",
    )
    assert result.primary_cause == "timing"
    assert result.confidence >= 0.7


def test_concurrency_pattern_data_race():
    result = classify_rule_based(
        log_text="ThreadSanitizer: data race on shared session counter",
        error_message="concurrent access detected",
    )
    assert result.primary_cause == "concurrency"
    assert result.confidence >= 0.85


def test_environment_pattern_connection_refused():
    result = classify_rule_based(
        log_text="ConnectionRefusedError: [Errno 111] Connection refused to redis:6379",
        error_message="redis.exceptions.ConnectionError",
    )
    assert result.primary_cause == "environment"
    assert result.confidence >= 0.7


def test_state_leakage_pattern_unique_violation():
    result = classify_rule_based(
        log_text="psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint",
        error_message="IntegrityError: already exists",
    )
    assert result.primary_cause == "state_leakage"
    assert result.confidence >= 0.7


def test_unknown_for_generic_error():
    result = classify_rule_based(
        log_text="AssertionError: expected True but got False",
        error_message="assertion failed",
    )
    assert result.primary_cause == "unknown"


def test_classify_failure_fallback_to_rule_based():
    # With use_ml=False, should use rule-based only
    result = classify_failure(
        log_output="TimeoutError: element not found within 5000ms",
        error_message="TimeoutError",
        use_ml=False,
    )
    assert result.primary_cause == "timing"
    assert result.classifier_version == "rule_based_v1"


def test_secondary_causes_populated():
    # A log with multiple signals
    result = classify_rule_based(
        log_text="TimeoutError: connection to redis timed out after 5000ms",
        error_message="redis connection timeout",
    )
    # Primary should be one of timing/environment
    assert result.primary_cause in ("timing", "environment")
    # Should have evidence
    assert result.evidence is not None
    assert "method" in result.evidence


def test_empty_log():
    result = classify_failure(log_output="", error_message="", use_ml=False)
    assert result.primary_cause == "unknown"