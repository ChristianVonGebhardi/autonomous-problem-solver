"""Tests for the scan worker and corpus matching."""
import os
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://licenseguard:licenseguard@localhost:5432/licenseguard")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key")

from unittest.mock import MagicMock, patch
from app.detector import CodeAnalysis, tokenize_code, compute_minhash, jaccard_similarity_from_minhash


def test_code_analysis_initialization():
    """Test that CodeAnalysis initializes correctly."""
    code = """
def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
"""
    analysis = CodeAnalysis(code, "python")
    assert len(analysis.tokens) > 0
    assert analysis.code_hash is not None
    assert analysis.normalized is not None


def test_minhash_near_duplicate_detection():
    """Test that similar code variants get high similarity scores."""
    original = """
def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)

def merge(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result
"""
    # Slightly modified version (renamed variables)
    variant = """
def merge_sort(array):
    if len(array) <= 1:
        return array
    mid = len(array) // 2
    left = merge_sort(array[:mid])
    right = merge_sort(array[mid:])
    return merge(left, right)

def merge(left, right):
    merged = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged
"""
    tokens_orig = tokenize_code(original, "python")
    tokens_var = tokenize_code(variant, "python")

    mh1 = compute_minhash(tokens_orig, num_perm=128)
    mh2 = compute_minhash(tokens_var, num_perm=128)

    if mh1 and mh2:
        sim = jaccard_similarity_from_minhash(mh1, mh2)
        assert sim > 0.5, f"Similar code variants should have >50% similarity, got {sim:.2%}"


def test_scan_risk_tier_from_matches():
    """Test that risk tier is correctly aggregated from matches."""
    from app.license_taxonomy import get_highest_risk_tier

    # High + low = high
    assert get_highest_risk_tier(["low", "high", "medium"]) == "high"
    # Only medium = medium
    assert get_highest_risk_tier(["low", "medium"]) == "medium"
    # Only low = low
    assert get_highest_risk_tier(["low"]) == "low"
    # Empty = clean
    assert get_highest_risk_tier([]) == "clean"


def test_remediation_template_fallback():
    """Test that remediation works without OpenAI key."""
    from app.remediation import get_remediation_suggestion

    result = get_remediation_suggestion(
        original_code="def sort(arr): arr.sort(); return arr",
        license_spdx="GPL-2.0-only",
        risk_tier="high",
        api_key=None
    )

    assert result["status"] == "template_only"
    assert result["explanation"] is not None
    assert "GPL" in result["explanation"] or "copyleft" in result["explanation"].lower()
    assert result["suggested_code"] is None


def test_license_taxonomy_completeness():
    """Test that all major licenses are covered."""
    from app.license_taxonomy import classify_license, TIER_HIGH, TIER_MEDIUM, TIER_LOW

    # High risk
    for lic in ["GPL-2.0-only", "GPL-3.0-only", "AGPL-3.0-only"]:
        tier, _ = classify_license(lic)
        assert tier == TIER_HIGH, f"{lic} should be HIGH risk"

    # Medium risk
    for lic in ["LGPL-2.1-only", "MPL-2.0", "EPL-2.0"]:
        tier, _ = classify_license(lic)
        assert tier == TIER_MEDIUM, f"{lic} should be MEDIUM risk"

    # Low risk
    for lic in ["MIT", "Apache-2.0", "BSD-3-Clause", "ISC"]:
        tier, _ = classify_license(lic)
        assert tier == TIER_LOW, f"{lic} should be LOW risk"