"""Pytest configuration and shared fixtures."""
import pytest
import os

# Set test environment variables before any app imports
os.environ.setdefault("DATABASE_URL", "postgresql://licenseguard:licenseguard@localhost:5432/licenseguard")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key")
os.environ.setdefault("OPENAI_API_KEY", "")


@pytest.fixture(autouse=False)
def mock_db():
    """Mock database session for unit tests."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock_query = MagicMock()
    mock_query.count.return_value = 5
    mock_query.filter.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = []
    mock_query.first.return_value = None
    mock.query.return_value = mock_query
    return mock