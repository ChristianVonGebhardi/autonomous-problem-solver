#!/usr/bin/env python3
"""
Quick smoke test for the ScopeGuard API.
Run with: python test_health.py
Make sure the server is running first: uvicorn app.main:app --reload
"""
import httpx
import json
import sys


BASE_URL = "http://localhost:8000"


def test_health():
    r = httpx.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    print("✅ Health check passed")


def test_register_and_login():
    # Register
    payload = {
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User",
        "hourly_rate": 150.0,
    }
    r = httpx.post(f"{BASE_URL}/api/auth/register", json=payload)
    if r.status_code == 400 and "already registered" in r.text:
        print("ℹ️  User already exists, logging in...")
    elif r.status_code == 201:
        print("✅ Registration passed")
    else:
        print(f"❌ Registration failed: {r.text}")
        return None

    # Login
    login_payload = {"email": "test@example.com", "password": "testpass123"}
    r = httpx.post(f"{BASE_URL}/api/auth/login", json=login_payload)
    assert r.status_code == 200
    token = r.json()["access_token"]
    print("✅ Login passed")
    return token


def test_authenticated_endpoints(token: str):
    headers = {"Authorization": f"Bearer {token}"}

    # Get contracts
    r = httpx.get(f"{BASE_URL}/api/contracts/", headers=headers)
    assert r.status_code == 200
    print(f"✅ Contracts endpoint: {len(r.json())} contracts")

    # Get violations
    r = httpx.get(f"{BASE_URL}/api/violations/", headers=headers)
    assert r.status_code == 200
    print(f"✅ Violations endpoint: {len(r.json())} violations")

    # Get dashboard stats
    r = httpx.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
    assert r.status_code == 200
    stats = r.json()
    print(f"✅ Dashboard stats: {json.dumps(stats, indent=2)}")

    # Get change orders
    r = httpx.get(f"{BASE_URL}/api/change-orders/", headers=headers)
    assert r.status_code == 200
    print(f"✅ Change orders endpoint: {len(r.json())} orders")


if __name__ == "__main__":
    print("🧪 Running ScopeGuard API smoke tests...\n")
    try:
        test_health()
        token = test_register_and_login()
        if token:
            test_authenticated_endpoints(token)
        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)