"""Tests for data models."""
import pytest
from core.models import (
    RiskLevel, Ecosystem, ValidationResult, ScanReport,
    RegistryResult, HeuristicResult, ReputationResult
)


class TestRiskLevel:
    def test_score_below_0_3_is_low(self):
        assert RiskLevel.from_score(0.0) == RiskLevel.LOW
        assert RiskLevel.from_score(0.1) == RiskLevel.LOW
        assert RiskLevel.from_score(0.29) == RiskLevel.LOW

    def test_score_0_3_to_0_6_is_medium(self):
        assert RiskLevel.from_score(0.3) == RiskLevel.MEDIUM
        assert RiskLevel.from_score(0.45) == RiskLevel.MEDIUM
        assert RiskLevel.from_score(0.59) == RiskLevel.MEDIUM

    def test_score_0_6_to_0_8_is_high(self):
        assert RiskLevel.from_score(0.6) == RiskLevel.HIGH
        assert RiskLevel.from_score(0.79) == RiskLevel.HIGH

    def test_score_0_8_plus_is_critical(self):
        assert RiskLevel.from_score(0.8) == RiskLevel.CRITICAL
        assert RiskLevel.from_score(1.0) == RiskLevel.CRITICAL


class TestValidationResult:
    def _make_result(self, risk_level=RiskLevel.LOW, policy_override=None):
        return ValidationResult(
            package_name="test-pkg",
            ecosystem="pypi",
            risk_score=0.1,
            risk_level=risk_level,
            exists_on_registry=True,
            policy_override=policy_override,
        )

    def test_low_risk_not_blocked(self):
        result = self._make_result(RiskLevel.LOW)
        assert not result.should_block
        assert not result.should_warn

    def test_medium_risk_warns(self):
        result = self._make_result(RiskLevel.MEDIUM)
        assert result.should_warn
        assert not result.should_block

    def test_high_risk_warns_not_blocked(self):
        result = self._make_result(RiskLevel.HIGH)
        assert result.should_warn
        assert not result.should_block

    def test_critical_risk_blocked(self):
        result = self._make_result(RiskLevel.CRITICAL)
        assert result.should_block

    def test_policy_allow_overrides_critical(self):
        result = self._make_result(RiskLevel.CRITICAL, policy_override="allow")
        assert not result.should_block
        assert not result.should_warn

    def test_policy_block_overrides_low(self):
        result = self._make_result(RiskLevel.LOW, policy_override="block")
        assert result.should_block

    def test_to_dict_structure(self):
        result = self._make_result()
        d = result.to_dict()
        assert "package_name" in d
        assert "risk_score" in d
        assert "risk_level" in d
        assert "exists_on_registry" in d
        assert "flags" in d


class TestScanReport:
    def _make_report(self, results):
        return ScanReport(
            manifest_path="requirements.txt",
            ecosystem="pypi",
            total_packages=len(results),
            results=results,
            scan_duration_ms=100.0,
        )

    def _make_result(self, risk_level, exists=True):
        return ValidationResult(
            package_name="pkg",
            ecosystem="pypi",
            risk_score=0.1,
            risk_level=risk_level,
            exists_on_registry=exists,
        )

    def test_blocked_count(self):
        results = [
            self._make_result(RiskLevel.CRITICAL),
            self._make_result(RiskLevel.LOW),
        ]
        report = self._make_report(results)
        assert report.blocked_count == 1

    def test_warned_count(self):
        results = [
            self._make_result(RiskLevel.HIGH),
            self._make_result(RiskLevel.MEDIUM),
            self._make_result(RiskLevel.LOW),
        ]
        report = self._make_report(results)
        assert report.warned_count == 2

    def test_clean_count(self):
        results = [
            self._make_result(RiskLevel.LOW),
            self._make_result(RiskLevel.LOW),
            self._make_result(RiskLevel.CRITICAL),
        ]
        report = self._make_report(results)
        assert report.clean_count == 2

    def test_not_found_count(self):
        results = [
            self._make_result(RiskLevel.CRITICAL, exists=False),
            self._make_result(RiskLevel.LOW, exists=True),
        ]
        report = self._make_report(results)
        assert report.not_found_count == 1

    def test_to_dict_structure(self):
        report = self._make_report([self._make_result(RiskLevel.LOW)])
        d = report.to_dict()
        assert "summary" in d
        assert "results" in d
        assert d["summary"]["total"] == 1