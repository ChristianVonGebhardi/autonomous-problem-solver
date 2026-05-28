"""Policy client — communicates with optional GuardRail Policy Server."""
from __future__ import annotations
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class PolicyClient:
    """
    Optional client for the GuardRail Policy Server.
    
    If no policy server is configured, all checks are performed locally.
    """

    def __init__(self, server_url: str, api_key: Optional[str] = None):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(5.0),
                headers={
                    "User-Agent": "guardrail-scanner/0.1.0",
                    **self._headers(),
                },
            )
        return self._client

    async def check(self, package_name: str, ecosystem: str) -> Optional[str]:
        """
        Check policy for a package.
        
        Returns:
            "allow" if explicitly allowed
            "block" if explicitly blocked
            None if no policy override
        """
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.server_url}/api/v1/policy/check",
                params={"package": package_name, "ecosystem": ecosystem},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("action")  # "allow", "block", or None
            return None
        except Exception as e:
            logger.debug("Policy server unreachable: %s", e)
            return None

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None