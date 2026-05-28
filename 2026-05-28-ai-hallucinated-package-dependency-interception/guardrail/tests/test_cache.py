"""Tests for the SQLite cache."""
import asyncio
import time
import pytest
import pytest_asyncio
from core.cache import Cache


@pytest_asyncio.fixture
async def cache(tmp_path):
    c = Cache(db_path=str(tmp_path / "test.db"), ttl=60)
    yield c
    await c.close()


class TestCacheOperations:
    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        await cache.set("key1", {"data": "value"})
        result = await cache.get("key1")
        assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, cache):
        result = await cache.get("nonexistent-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_entry_returns_none(self, cache):
        await cache.set("expiring", "soon", ttl=1)
        # Manually expire by setting a past TTL
        await cache._db.execute(
            "UPDATE cache SET expires_at = ? WHERE key = ?",
            (time.time() - 1, "expiring")
        )
        await cache._db.commit()
        result = await cache.get("expiring")
        assert result is None

    @pytest.mark.asyncio
    async def test_overwrite_existing(self, cache):
        await cache.set("key", "first")
        await cache.set("key", "second")
        result = await cache.get("key")
        assert result == "second"

    @pytest.mark.asyncio
    async def test_delete_key(self, cache):
        await cache.set("deleteme", "value")
        await cache.delete("deleteme")
        result = await cache.get("deleteme")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear_all(self, cache):
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None

    @pytest.mark.asyncio
    async def test_purge_expired(self, cache):
        await cache.set("fresh", "value", ttl=3600)
        await cache.set("stale", "value", ttl=1)
        # Force stale entry to expire
        await cache._db.execute(
            "UPDATE cache SET expires_at = ? WHERE key = ?",
            (time.time() - 1, "stale")
        )
        await cache._db.commit()
        
        deleted = await cache.purge_expired()
        assert deleted == 1
        assert await cache.get("fresh") is not None
        assert await cache.get("stale") is None

    @pytest.mark.asyncio
    async def test_complex_values(self, cache):
        value = {
            "packages": ["a", "b", "c"],
            "metadata": {"version": "1.0", "count": 42},
            "exists": True,
        }
        await cache.set("complex", value)
        result = await cache.get("complex")
        assert result == value

    @pytest.mark.asyncio
    async def test_context_manager(self, tmp_path):
        async with Cache(db_path=str(tmp_path / "ctx.db"), ttl=60) as c:
            await c.set("x", 42)
            result = await c.get("x")
        assert result == 42