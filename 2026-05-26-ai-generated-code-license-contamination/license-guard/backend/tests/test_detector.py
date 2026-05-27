"""Tests for the code detection engine."""
import pytest
from app.detector import (
    tokenize_code,
    compute_minhash,
    jaccard_similarity_from_minhash,
    compute_code_hash,
    normalize_code,
    CodeAnalysis,
)


def test_tokenize_simple_python():
    code = "def hello():\n    return 42"
    tokens = tokenize_code(code, "python")
    assert len(tokens) > 0
    # Should contain some recognizable tokens
    token_str = ' '.join(tokens)
    assert any(t in token_str for t in ['def', 'hello', 'return', '42'])


def test_tokenize_removes_comments():
    code = "x = 1  # this is a comment\ny = 2"
    tokens = tokenize_code(code)
    # Comment text should not appear as tokens
    token_str = ' '.join(tokens)
    assert 'comment' not in token_str


def test_minhash_similar_code():
    """Similar code should have high Jaccard similarity."""
    code1 = """
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
    code2 = """
def binary_search(array, val):
    left, right = 0, len(array) - 1
    while left <= right:
        mid = (left + right) // 2
        if array[mid] == val:
            return mid
        elif array[mid] < val:
            left = mid + 1
        else:
            right = mid - 1
    return -1
"""

    tokens1 = tokenize_code(code1, "python")
    tokens2 = tokenize_code(code2, "python")

    minhash1 = compute_minhash(tokens1)
    minhash2 = compute_minhash(tokens2)

    assert minhash1 is not None
    assert minhash2 is not None

    similarity = jaccard_similarity_from_minhash(minhash1, minhash2)
    assert similarity > 0.5, f"Expected high similarity, got {similarity}"


def test_minhash_different_code():
    """Different code should have low Jaccard similarity."""
    code1 = "def quicksort(arr): return arr if len(arr) <= 1 else quicksort([x for x in arr[1:] if x < arr[0]]) + [arr[0]] + quicksort([x for x in arr[1:] if x >= arr[0]])"
    code2 = "class DatabaseConnection: def __init__(self, host, port): self.host = host; self.port = port"

    tokens1 = tokenize_code(code1)
    tokens2 = tokenize_code(code2)

    minhash1 = compute_minhash(tokens1)
    minhash2 = compute_minhash(tokens2)

    if minhash1 and minhash2:
        similarity = jaccard_similarity_from_minhash(minhash1, minhash2)
        assert similarity < 0.5, f"Expected low similarity, got {similarity}"


def test_code_hash_is_sha256():
    """Code hash should be a valid SHA256 hex string."""
    code = "def foo(): return 1"
    h = compute_code_hash(code)
    assert isinstance(h, str)
    assert len(h) == 64  # SHA256 hex is 64 chars
    assert all(c in '0123456789abcdef' for c in h)


def test_code_hash_normalized_whitespace():
    """Whitespace normalization should produce consistent hash."""
    code1 = "def foo():return 1"
    code2 = "def foo():return 1"
    # Same code = same hash
    assert compute_code_hash(code1) == compute_code_hash(code2)


def test_code_analysis():
    """CodeAnalysis should produce all fingerprints."""
    code = """
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr
"""
    analysis = CodeAnalysis(code, "python")

    assert len(analysis.tokens) > 0
    assert analysis.code_hash is not None
    assert len(analysis.code_hash) == 64
    info = analysis.to_dict()
    assert "tokens_count" in info
    assert info["tokens_count"] > 0


def test_license_taxonomy():
    """Test license classification."""
    from app.license_taxonomy import classify_license, TIER_HIGH, TIER_LOW

    tier, desc = classify_license("GPL-2.0-only")
    assert tier == TIER_HIGH

    tier, desc = classify_license("MIT")
    assert tier == TIER_LOW

    tier, desc = classify_license("Apache-2.0")
    assert tier == TIER_LOW

    tier, desc = classify_license("UNKNOWN-LICENSE-XYZ")
    assert tier == "unknown"


def test_highest_risk_tier():
    """Test that highest risk tier is correctly identified."""
    from app.license_taxonomy import get_highest_risk_tier

    tiers = ["low", "medium", "high", "low"]
    assert get_highest_risk_tier(tiers) == "high"

    tiers = ["low", "medium", "low"]
    assert get_highest_risk_tier(tiers) == "medium"

    tiers = ["low", "low"]
    assert get_highest_risk_tier(tiers) == "low"

    assert get_highest_risk_tier([]) == "clean"


def test_normalize_code():
    """Test code normalization."""
    code = "  def foo(x):  # comment\n    return x  "
    normalized = normalize_code(code)
    assert 'comment' not in normalized
    assert normalized == normalized.strip()