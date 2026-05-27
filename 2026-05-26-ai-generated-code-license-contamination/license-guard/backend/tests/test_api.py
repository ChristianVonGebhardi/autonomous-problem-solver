"""Tests for the FastAPI endpoints."""
import pytest
import os

os.environ.setdefault("DATABASE_URL", "postgresql://licenseguard:licenseguard@localhost:5432/licenseguard")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key")

from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


# Mock database for testing
def get_mock_db():
    mock_db = MagicMock()
    # Mock query chain for health check
    mock_query = MagicMock()
    mock_query.count.return_value = 5
    mock_query.filter.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = []
    mock_query.first.return_value = None
    mock_db.query.return_value = mock_query
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
    assert "docs" in data


def test_scan_request_validation(client):
    """Test that invalid scan requests are rejected."""
    # Empty code should fail
    response = client.post("/api/v1/scan/sync", json={
        "code": "",
        "language": "python",
        "source": "api"
    })
    assert response.status_code == 422


def test_scan_requires_code(client):
    """Test scan endpoint requires code field."""
    response = client.post("/api/v1/scan/sync", json={
        "language": "python",
        "source": "api"
    })
    assert response.status_code == 422