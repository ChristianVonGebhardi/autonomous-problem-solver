"""Tests for the FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# We need to mock DB before importing the app
import sys
from unittest.mock import MagicMock

# Mock database for testing
mock_db = MagicMock()


def get_mock_db():
    yield mock_db


@pytest.fixture
def client():
    from app.main import app
    from app.database import get_db
    app.dependency_overrides[get_db] = get_mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "LicenseGuard"


def test_scan_request_validation(client):
    """Test that invalid scan requests are rejected."""
    # Empty code should fail
    response = client.post("/api/v1/scan/sync", json={
        "code": "",
        "language": "python"
    })
    assert response.status_code == 422


def test_scan_requires_code(client):
    """Test scan endpoint requires code field."""
    response = client.post("/api/v1/scan/sync", json={
        "language": "python"
    })
    assert response.status_code == 422