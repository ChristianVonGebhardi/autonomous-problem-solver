"""Registry existence checker — queries PyPI, npm, crates.io, Go module proxy, Maven Central."""
from __future__ import annotations
import asyncio
import logging
from typing import Optional, Dict, Any
from urllib.parse import quote

import httpx

from .cache import Cache
from .models import Ecosystem, RegistryResult

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class RegistryChecker:
    """
    Checks whether a package exists on the appropriate registry.
    Uses a shared httpx.AsyncClient and SQLite cache.
    """

    def __init__(self, cache: Cache, client: Optional[httpx.AsyncClient] = None):
        self.cache = cache
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=TIMEOUT,
                headers={
                    "User-Agent": "guardrail-scanner/0.1.0 (https://github.com/guardrail-dev/guardrail)",
                    "Accept": "application/json",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._owns_client and self._client:
            await self._client.aclose()
            self._client = None

    async def check(self, package_name: str, ecosystem: Ecosystem) -> RegistryResult:
        """Check if package exists on the registry."""
        cache_key = f"registry:{ecosystem.value}:{package_name.lower()}"
        cached = await self.cache.get(cache_key)
        if cached:
            return RegistryResult(**cached)

        result = await self._do_check(package_name, ecosystem)
        await self.cache.set(cache_key, {
            "exists": result.exists,
            "ecosystem": result.ecosystem,
            "package_name": result.package_name,
            "error": result.error,
            "metadata": result.metadata,
        })
        return result

    async def _do_check(self, package_name: str, ecosystem: Ecosystem) -> RegistryResult:
        dispatch = {
            Ecosystem.PYPI: self._check_pypi,
            Ecosystem.NPM: self._check_npm,
            Ecosystem.CARGO: self._check_crates,
            Ecosystem.GO: self._check_go,
            Ecosystem.MAVEN: self._check_maven,
        }
        checker = dispatch.get(ecosystem)
        if not checker:
            return RegistryResult(
                exists=False,
                ecosystem=ecosystem.value,
                package_name=package_name,
                error=f"Unsupported ecosystem: {ecosystem.value}",
            )
        return await checker(package_name)

    async def _check_pypi(self, package_name: str) -> RegistryResult:
        client = await self._get_client()
        url = f"https://pypi.org/pypi/{quote(package_name)}/json"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                info = data.get("info", {})
                # Get last release date
                releases = data.get("releases", {})
                latest_date = None
                download_approx = None
                if releases:
                    all_dates = []
                    for version_files in releases.values():
                        for f in version_files:
                            if f.get("upload_time"):
                                all_dates.append(f["upload_time"])
                    if all_dates:
                        latest_date = sorted(all_dates)[-1]

                return RegistryResult(
                    exists=True,
                    ecosystem=Ecosystem.PYPI.value,
                    package_name=package_name,
                    metadata={
                        "version": info.get("version"),
                        "summary": info.get("summary", "")[:200],
                        "author": info.get("author"),
                        "home_page": info.get("home_page"),
                        "project_url": info.get("project_url"),
                        "requires_python": info.get("requires_python"),
                        "classifiers": info.get("classifiers", [])[:5],
                        "latest_upload_date": latest_date,
                        "maintainer": info.get("maintainer"),
                    },
                )
            elif resp.status_code == 404:
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.PYPI.value,
                    package_name=package_name,
                )
            else:
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.PYPI.value,
                    package_name=package_name,
                    error=f"HTTP {resp.status_code}",
                )
        except httpx.TimeoutException:
            return RegistryResult(
                exists=False,
                ecosystem=Ecosystem.PYPI.value,
                package_name=package_name,
                error="Request timeout",
            )
        except Exception as e:
            logger.warning("PyPI check failed for %s: %s", package_name, e)
            return RegistryResult(
                exists=False,
                ecosystem=Ecosystem.PYPI.value,
                package_name=package_name,
                error=str(e),
            )

    async def _check_npm(self, package_name: str) -> RegistryResult:
        client = await self._get_client()
        # Handle scoped packages like @scope/name
        encoded = quote(package_name.replace("/", "%2F"), safe="@%")
        url = f"https://registry.npmjs.org/{encoded}"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                dist_tags = data.get("dist-tags", {})
                latest = dist_tags.get("latest", "")
                versions = list(data.get("versions", {}).keys())
                time_data = data.get("time", {})
                created = time_data.get("created")
                modified = time_data.get("modified")
                latest_version_info = data.get("versions", {}).get(latest, {})
                maintainers = data.get("maintainers", [])
                return RegistryResult(
                    exists=True,
                    ecosystem=Ecosystem.NPM.value,
                    package_name=package_name,
                    metadata={
                        "latest_version": latest,
                        "version_count": len(versions),
                        "created": created,
                        "modified": modified,
                        "description": data.get("description", "")[:200],
                        "homepage": latest_version_info.get("homepage"),
                        "repository": latest_version_info.get("repository", {}).get("url") if isinstance(latest_version_info.get("repository"), dict) else None,
                        "maintainer_count": len(maintainers),
                        "maintainers": [m.get("name") for m in maintainers[:5]],
                    },
                )
            elif resp.status_code == 404:
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.NPM.value,
                    package_name=package_name,
                )
            else:
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.NPM.value,
                    package_name=package_name,
                    error=f"HTTP {resp.status_code}",
                )
        except httpx.TimeoutException:
            return RegistryResult(
                exists=False,
                ecosystem=Ecosystem.NPM.value,
                package_name=package_name,
                error="Request timeout",
            )
        except Exception as e:
            logger.warning("npm check failed for %s: %s", package_name, e)
            return RegistryResult(
                exists=False,
                ecosystem=Ecosystem.NPM.value,
                package_name=package_name,
                error=str(e),
            )

    async def _check_crates(self, package_name: str) -> RegistryResult:
        client = await self._get_client()
        url = f"https://crates.io/api/v1/crates/{quote(package_name)}"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                krate = data.get("crate", {})
                return RegistryResult(
                    exists=True,
                    ecosystem=Ecosystem.CARGO.value,
                    package_name=package_name,
                    metadata={
                        "max_version": krate.get("max_version"),
                        "downloads": krate.get("downloads"),
                        "recent_downloads": krate.get("recent_downloads"),
                        "created_at": krate.get("created_at"),
                        "updated_at": krate.get("updated_at"),
                        "description": (krate.get("description") or "")[:200],
                        "homepage": krate.get("homepage"),
                        "repository": krate.get("repository"),
                    },
                )
            elif resp.status_code == 404:
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.CARGO.value,
                    package_name=package_name,
                )
            else:
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.CARGO.value,
                    package_name=package_name,
                    error=f"HTTP {resp.status_code}",
                )
        except httpx.TimeoutException:
            return RegistryResult(
                exists=False,
                ecosystem=Ecosystem.CARGO.value,
                package_name=package_name,
                error="Request timeout",
            )
        except Exception as e:
            logger.warning("crates.io check failed for %s: %s", package_name, e)
            return RegistryResult(
                exists=False,
                ecosystem=Ecosystem.CARGO.value,
                package_name=package_name,
                error=str(e),
            )

    async def _check_go(self, package_name: str) -> RegistryResult:
        client = await self._get_client()
        # Go module proxy: https://proxy.golang.org/{module}/@latest
        url = f"https://proxy.golang.org/{quote(package_name, safe='/')}/@latest"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return RegistryResult(
                    exists=True,
                    ecosystem=Ecosystem.GO.value,
                    package_name=package_name,
                    metadata={
                        "version": data.get("Version"),
                        "time": data.get("Time"),
                        "origin": data.get("Origin"),
                    },
                )
            elif resp.status_code in (404, 410):
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.GO.value,
                    package_name=package_name,
                )
            else:
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.GO.value,
                    package_name=package_name,
                    error=f"HTTP {resp.status_code}",
                )
        except httpx.TimeoutException:
            return RegistryResult(
                exists=False,
                ecosystem=Ecosystem.GO.value,
                package_name=package_name,
                error="Request timeout",
            )
        except Exception as e:
            logger.warning("Go proxy check failed for %s: %s", package_name, e)
            return RegistryResult(
                exists=False,
                ecosystem=Ecosystem.GO.value,
                package_name=package_name,
                error=str(e),
            )

    async def _check_maven(self, package_name: str) -> RegistryResult:
        """Check Maven Central. package_name should be groupId:artifactId."""
        client = await self._get_client()
        # Maven Central search API
        parts = package_name.split(":")
        if len(parts) == 2:
            group_id, artifact_id = parts
            query = f"g:{quote(group_id)}+AND+a:{quote(artifact_id)}"
        else:
            query = f"a:{quote(package_name)}"
        url = f"https://search.maven.org/solrsearch/select?q={query}&rows=1&wt=json"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                num_found = data.get("response", {}).get("numFound", 0)
                if num_found > 0:
                    doc = data["response"]["docs"][0]
                    return RegistryResult(
                        exists=True,
                        ecosystem=Ecosystem.MAVEN.value,
                        package_name=package_name,
                        metadata={
                            "group_id": doc.get("g"),
                            "artifact_id": doc.get("a"),
                            "latest_version": doc.get("latestVersion"),
                            "version_count": doc.get("versionCount"),
                            "timestamp": doc.get("timestamp"),
                        },
                    )
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.MAVEN.value,
                    package_name=package_name,
                )
            else:
                return RegistryResult(
                    exists=False,
                    ecosystem=Ecosystem.MAVEN.value,
                    package_name=package_name,
                    error=f"HTTP {resp.status_code}",
                )
        except Exception as e:
            logger.warning("Maven check failed for %s: %s", package_name, e)
            return RegistryResult(
                exists=False,
                ecosystem=Ecosystem.MAVEN.value,
                package_name=package_name,
                error=str(e),
            )