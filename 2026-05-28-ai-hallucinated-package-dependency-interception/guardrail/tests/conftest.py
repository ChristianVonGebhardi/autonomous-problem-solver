"""pytest configuration and shared fixtures."""
import pytest


def pytest_configure(config):
    """Register custom marks."""
    config.addinistrequiredversion = False


# Configure asyncio mode
def pytest_collection_modifyitems(items):
    for item in items:
        if item.get_closest_marker("asyncio"):
            item.add_marker(pytest.mark.asyncio)