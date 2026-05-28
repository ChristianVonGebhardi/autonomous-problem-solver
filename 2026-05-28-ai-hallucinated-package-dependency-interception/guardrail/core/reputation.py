"""
Package Reputation Scorer.

Fetches and scores package reputation based on:
- Download count (more = safer)
- Age since first publish (older = safer)
- Number of maintainers
- Presence of GitHub/source repository
"""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import httpx

from .cache import Cache
from .models import Ecosystem, ReputationResult, RegistryResult

logger = logging.getLogger(__name__)


class ReputationScorer:
    """Scores package reputation using registry metadata."""

    def __init__(self, cache: Cache, client: Optional[httpx.AsyncClient] = None):
        self.cache = cache
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                headers={
                    "User-Agent": "guardrail-scanner/0.1.0",
                    "Accept": "application/json",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._owns_client and self._client:
            await self._client.aclose()
            self._client = None

    async def score(
        self,
        package_name: str,
        ecosystem: Ecosystem,
        registry_result: Optional[RegistryResult] = None,
    ) -> ReputationResult:
        """Score package reputation. Uses registry_result metadata if available."""
        
        if registry_result and not registry_result.exists:
            # Non-existent package → maximum reputation risk
            return ReputationResult(
                score=1.0,
                flags=["package-not-found"],
            )

        cache_key = f"reputation:{ecosystem.value}:{package_name.lower()}"
        cached = await self.cache.get(cache_key)
        if cached:
            return ReputationResult(**cached)

        result = await self._score_by_ecosystem(package_name, ecosystem, registry_result)
        
        # Cache reputation data (shorter TTL for reputation since it changes faster)
        await self.cache.set(cache_key, {
            "score": result.score,
            "download_count": result.download_count,
            "days_since_publish": result.days_since_publish,
            "maintainer_count": result.maintainer_count,
            "has_github": result.has_github,
            "flags": result.flags,
        }, ttl=1800)  # 30 min TTL
        
        return result

    async def _score_by_ecosystem(
        self,
        package_name: str,
        ecosystem: Ecosystem,
        registry_result: Optional[RegistryResult],
    ) -> ReputationResult:
        metadata = registry_result.metadata if registry_result else {}
        
        dispatch = {
            Ecosystem.PYPI: self._score_pypi,
            Ecosystem.NPM: self._score_npm,
            Ecosystem.CARGO: self._score_cargo,
        }
        
        scorer = dispatch.get(ecosystem)
        if scorer:
            return await scorer(package_name, metadata)
        else:
            # For unsupported ecosystems, return neutral score
            return ReputationResult(score=0.5, flags=["unsupported-ecosystem-reputation"])

    async def _score_pypi(
        self, package_name: str, metadata: Dict[str, Any]
    ) -> ReputationResult:
        """Score PyPI package reputation using PyPI stats API."""
        flags: List[str] = []
        
        # Try to get download stats from PyPI Stats
        client = await self._get_client()
        downloads = None
        try:
            stats_url = f"https://pypistats.org/api/packages/{package_name.lower()}/recent"
            resp = await client.get(stats_url)
            if resp.status_code == 200:
                stats = resp.json()
                downloads = stats.get("data", {}).get("last_month", 0)
        except Exception as e:
            logger.debug("Could not fetch PyPI stats for %s: %s", package_name, e)

        # Parse publish date
        days_old = None
        latest_date_str = metadata.get("latest_upload_date")
        if latest_date_str:
            try:
                latest_date = datetime.fromisoformat(latest_date_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_old = (now - latest_date).days
            except Exception:
                pass

        # Check for GitHub link
        home_page = metadata.get("home_page", "") or ""
        project_url = metadata.get("project_url", "") or ""
        has_github = (
            "github.com" in home_page.lower() or
            "github.com" in project_url.lower()
        )

        maintainer = metadata.get("maintainer") or metadata.get("author")
        maintainer_count = 1 if maintainer else 0

        return self._compute_score(
            downloads=downloads,
            days_old=days_old,
            maintainer_count=maintainer_count,
            has_github=has_github,
            flags=flags,
        )

    async def _score_npm(
        self, package_name: str, metadata: Dict[str, Any]
    ) -> ReputationResult:
        """Score npm package reputation."""
        flags: List[str] = []
        
        # Try npm download stats
        client = await self._get_client()
        downloads = None
        try:
            from urllib.parse import quote
            encoded = quote(package_name.replace("/", "%2F"), safe="@%")
            stats_url = f"https://api.npmjs.org/downloads/point/last-month/{encoded}"
            resp = await client.get(stats_url)
            if resp.status_code == 200:
                stats = resp.json()
                downloads = stats.get("downloads", 0)
        except Exception as e:
            logger.debug("Could not fetch npm stats for %s: %s", package_name, e)

        # Parse dates from metadata
        days_old = None
        created_str = metadata.get("created")
        if created_str:
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_old = (now - created).days
            except Exception:
                pass

        maintainer_count = metadata.get("maintainer_count", 0)
        
        repository = metadata.get("repository", "") or ""
        has_github = "github.com" in repository.lower()

        return self._compute_score(
            downloads=downloads,
            days_old=days_old,
            maintainer_count=maintainer_count,
            has_github=has_github,
            flags=flags,
        )

    async def _score_cargo(
        self, package_name: str, metadata: Dict[str, Any]
    ) -> ReputationResult:
        """Score crates.io package reputation."""
        flags: List[str] = []
        
        downloads = metadata.get("downloads")
        
        days_old = None
        created_str = metadata.get("created_at")
        if created_str:
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_old = (now - created).days
            except Exception:
                pass

        repository = metadata.get("repository", "") or ""
        homepage = metadata.get("homepage", "") or ""
        has_github = (
            "github.com" in repository.lower() or
            "github.com" in homepage.lower()
        )

        return self._compute_score(
            downloads=downloads,
            days_old=days_old,
            maintainer_count=None,  # Not easily available from basic API
            has_github=has_github,
            flags=flags,
        )

    def _compute_score(
        self,
        downloads: Optional[int],
        days_old: Optional[int],
        maintainer_count: Optional[int],
        has_github: bool,
        flags: List[str],
    ) -> ReputationResult:
        """
        Compute a 0-1 risk score from reputation signals.
        Higher score = more risk (less reputable).
        """
        score = 0.0
        
        # Download count scoring (inverted: low downloads = higher risk)
        dl_score = 0.3  # default: unknown
        if downloads is not None:
            if downloads >= 1_000_000:
                dl_score = 0.0
            elif downloads >= 100_000:
                dl_score = 0.05
            elif downloads >= 10_000:
                dl_score = 0.1
            elif downloads >= 1_000:
                dl_score = 0.2
            elif downloads >= 100:
                dl_score = 0.4
            elif downloads >= 10:
                dl_score = 0.65
                flags.append("very-low-downloads")
            else:
                dl_score = 0.85
                flags.append("almost-no-downloads")

        # Age scoring (newer = higher risk)
        age_score = 0.3  # default: unknown
        if days_old is not None:
            if days_old >= 365 * 3:  # 3+ years
                age_score = 0.0
            elif days_old >= 365:  # 1-3 years
                age_score = 0.05
            elif days_old >= 180:  # 6 months - 1 year
                age_score = 0.1
            elif days_old >= 30:  # 1-6 months
                age_score = 0.3
            elif days_old >= 7:  # 1-4 weeks
                age_score = 0.6
                flags.append("recently-published")
            else:  # < 1 week
                age_score = 0.9
                flags.append("published-this-week")

        # Maintainer count scoring
        maint_score = 0.2  # default: unknown
        if maintainer_count is not None:
            if maintainer_count >= 5:
                maint_score = 0.0
            elif maintainer_count >= 2:
                maint_score = 0.05
            elif maintainer_count == 1:
                maint_score = 0.15
            else:
                maint_score = 0.4
                flags.append("no-maintainer-listed")

        # GitHub presence
        github_score = 0.0 if has_github else 0.2
        if not has_github:
            flags.append("no-github-link")

        # Weighted combination
        combined = (
            dl_score * 0.4 +
            age_score * 0.35 +
            maint_score * 0.15 +
            github_score * 0.1
        )

        return ReputationResult(
            score=min(combined, 1.0),
            download_count=downloads,
            days_since_publish=days_old,
            maintainer_count=maintainer_count,
            has_github=has_github,
            flags=flags,
        )