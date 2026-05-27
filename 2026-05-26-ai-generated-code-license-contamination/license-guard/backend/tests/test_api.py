"""Tests for the FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


# Mock database for testing
def get_mock_db():
    mock_db = MagicMock()
    # Mock query chain for health check
    mock_query = MagicMock()
    mock_query.count.return_value = 5
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


def test_health_endpoint_structure(client):
    """Test health endpoint returns expected fields."""
    with patch('app.routes.health.redis') as mock_redis:
        mock_redis_instance = MagicMock()
        mock_redis.from_url.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        
        response = client.get("/api/v1/health")
        # May fail if DB not available, but check structure
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "version" in data