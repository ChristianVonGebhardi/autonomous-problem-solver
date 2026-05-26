"""
End-to-end demo of the LicenseGuard detection pipeline.
Run this after starting the backend: python scripts/demo.py
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def demo_detection_pipeline():
    """Demonstrate the core detection pipeline without HTTP."""
    print("=" * 60)
    print("LicenseGuard - Detection Pipeline Demo")
    print("=" * 60)

    # Test code snippets
    test_cases = [
        {
            "name": "GPL-3.0 Heap Sort (Python CPython)",
            "expected_risk": "high",
            "code": """def heappush(heap, item):
    \"\"\"Push item onto heap, maintaining the heap invariant.\"\"\"
    heap.append(item)
    _siftdown(heap, 0, len(heap)-1)

def heappop(heap):
    \"\"\"Pop the smallest item off the heap, maintaining the heap invariant.\"\"\"
    lastelt = heap.pop()
    if heap:
        returnitem = heap[0]
        heap[0] = lastelt
        _siftup(heap, 0)
        return returnitem
    return lastelt""",
        },
        {
            "name": "MIT Lodash Debounce (JavaScript)",
            "expected_risk": "low",
            "code": """function debounce(func, wait, options) {
  let lastArgs, lastThis, result, timerId, lastCallTime;
  let lastInvokeTime = 0;
  let leading = false;
  let trailing = true;
  if (typeof func !== 'function') {
    throw new TypeError('Expected a function');
  }
  wait = +wait || 0;
  function invokeFunc(time) {
    const args = lastArgs;
    const thisArg = lastThis;
    lastArgs = lastThis = undefined;
    lastInvokeTime = time;
    result = func.apply(thisArg, args);
    return result;
  }
  return invokeFunc;
}""",
        },
        {
            "name": "Clean Custom Code",
            "expected_risk": "clean",
            "code": """def calculate_compound_interest(principal, rate, periods):
    \"\"\"
    Calculate compound interest.
    
    Args:
        principal: Initial investment amount
        rate: Annual interest rate (as decimal, e.g. 0.05 for 5%)
        periods: Number of compounding periods (years)
    
    Returns:
        Total amount after compound interest
    \"\"\"
    if principal < 0 or rate < 0 or periods < 0:
        raise ValueError("All parameters must be non-negative")
    return principal * (1 + rate) ** periods""",
        },
    ]

    print("\n1. Testing Code Analyzer (tokenization + fingerprinting):\n")
    from app.detector import CodeAnalysis, jaccard_similarity_from_minhash

    for case in test_cases:
        print(f"  Analyzing: {case['name']}")
        analysis = CodeAnalysis(case["code"], "python")
        print(f"    Tokens: {len(analysis.tokens)}")
        print(f"    Has MinHash: {analysis.minhash is not None}")
        print(f"    Has Embedding: {analysis.embedding is not None}")
        print(f"    Code Hash: {analysis.code_hash[:16]}...")
        print()

    print("2. Testing License Taxonomy:\n")
    from app.license_taxonomy import classify_license, get_highest_risk_tier

    test_licenses = [
        ("GPL-2.0-only", "high"),
        ("AGPL-3.0-only", "high"),
        ("LGPL-2.1-only", "medium"),
        ("MPL-2.0", "medium"),
        ("MIT", "low"),
        ("Apache-2.0", "low"),
        ("BSD-3-Clause", "low"),
    ]

    for spdx, expected_tier in test_licenses:
        tier, desc = classify_license(spdx)
        status = "✅" if tier == expected_tier else "❌"
        print(f"  {status} {spdx}: {tier} ({desc})")

    print()
    print("3. Testing MinHash Similarity:\n")
    from app.detector import tokenize_code, compute_minhash

    # Similar code should have high similarity
    code_a = """def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1"""

    code_b = """def binary_search(array, val):
    left, right = 0, len(array) - 1
    while left <= right:
        mid = (left + right) // 2
        if array[mid] == val:
            return mid
        elif array[mid] < val:
            left = mid + 1
        else:
            right = mid - 1
    return -1"""

    tokens_a = tokenize_code(code_a, "python")
    tokens_b = tokenize_code(code_b, "python")
    minhash_a = compute_minhash(tokens_a)
    minhash_b = compute_minhash(tokens_b)

    if minhash_a and minhash_b:
        sim = jaccard_similarity_from_minhash(minhash_a, minhash_b)
        print(f"  Binary search variants similarity: {sim:.1%}")
        status = "✅" if sim > 0.5 else "❌"
        print(f"  {status} Expected > 50%, got {sim:.1%}")
    else:
        print("  ⚠️  MinHash not available")

    print()
    print("4. Testing API (requires running backend):\n")
    try:
        import httpx

        with httpx.Client(base_url="http://localhost:8000", timeout=30) as client:
            # Health check
            resp = client.get("/api/v1/health")
            health = resp.json()
            print(f"  Health: {health['status']}")
            print(f"  Corpus size: {health['corpus_size']} snippets")

            if health["corpus_size"] == 0:
                print("\n  ⚠️  Corpus is empty! Run: python scripts/seed_corpus.py")
                return

            print()
            for case in test_cases:
                print(f"  Scanning: {case['name']}")
                resp = client.post(
                    "/api/v1/scan/sync",
                    json={
                        "code": case["code"],
                        "language": "python",
                        "source": "api",
                    },
                )
                result = resp.json()
                tier = result.get("risk_tier", "unknown")
                matches = len(result.get("matches", []))
                expected = case["expected_risk"]
                status = "✅" if tier == expected else f"⚠️  (expected {expected})"
                print(f"    Risk Tier: {tier} {status}")
                print(f"    Matches: {matches}")
                if matches > 0:
                    top = result["matches"][0]
                    print(f"    Top Match: {top['license_spdx']} ({top['similarity_score']:.1%} similar)")
                print()

    except Exception as e:
        print(f"  ⚠️  API not reachable: {e}")
        print("  Start backend first: docker compose up -d")

    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    demo_detection_pipeline()