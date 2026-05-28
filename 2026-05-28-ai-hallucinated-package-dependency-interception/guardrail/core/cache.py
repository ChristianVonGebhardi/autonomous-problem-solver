"""SQLite-backed cache with TTL support for registry API responses."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path.home() / ".guardrail" / "cache.db"
DEFAULT_TTL = 900  # 15 minutes


class Cache:
    """Async SQLite cache with TTL."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        ttl: int = DEFAULT_TTL,
    ):
        self.db_path = Path(db_path or os.environ.get("GUARDRAIL_CACHE_DB", str(DEFAULT_CACHE_PATH)))
        self.ttl = int(os.environ.get("GUARDRAIL_CACHE_TTL", ttl))
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def _ensure_open(self):
        if self._db is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(str(self.db_path))
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)
            """)
            await self._db.commit()
            logger.debug("Cache opened at %s", self.db_path)

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            await self._ensure_open()
            now = time.time()
            async with self._db.execute(
                "SELECT value FROM cache WHERE key = ? AND expires_at > ?",
                (key, now)
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                logger.debug("Cache HIT: %s", key)
                return json.loads(row[0])
            logger.debug("Cache MISS: %s", key)
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        async with self._lock:
            await self._ensure_open()
            expires_at = time.time() + (ttl or self.ttl)
            await self._db.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), expires_at)
            )
            await self._db.commit()
            logger.debug("Cache SET: %s (expires in %ds)", key, ttl or self.ttl)

    async def delete(self, key: str) -> None:
        async with self._lock:
            await self._ensure_open()
            await self._db.execute("DELETE FROM cache WHERE key = ?", (key,))
            await self._db.commit()

    async def purge_expired(self) -> int:
        async with self._lock:
            await self._ensure_open()
            cursor = await self._db.execute(
                "DELETE FROM cache WHERE expires_at <= ?", (time.time(),)
            )
            await self._db.commit()
            deleted = cursor.rowcount
            if deleted:
                logger.info("Purged %d expired cache entries", deleted)
            return deleted

    async def clear(self) -> None:
        async with self._lock:
            await self._ensure_open()
            await self._db.execute("DELETE FROM cache")
            await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self):
        await self._ensure_open()
        return self

    async def __aexit__(self, *args):
        await self.close()