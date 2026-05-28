"""Integration tests for the validator engine (uses mocked HTTP)."""
from __future__ import annotations
import json
import pytest
import pytest_asyncio
import httpx
import respx

from core.validator import Validator
from core.cache import Cache
from core.models import Ecosystem, RiskLevel


@pytest_asyncio.fixture
async def cache(tmp_path):
    """In-memory-ish cache for tests."""
    c = Cache(db_path=str(tmp_path / "test_cache.db"), ttl=60)
    yield c
    await c.close()


@pytest_asyncio.fixture
async def validator(cache):
    v = Validator(cache=cache)
    async with v:
        yield v


# ─── Mock responses ───

PYPI_EXISTS_RESPONSE = {
    "info": {
        "name": "requests",
        "version": "2.31.0",
        "summary": "Python HTTP for Humans.",
        "author": "Kenneth Reitz",
        "home_page": "https://requests.readthedocs.io",
        "project_url": "https://github.com/psf/requests",
        "requires_python": ">=3.7",
        "classifiers": [],
        "maintainer": "Kenneth Reitz",
    },
    "releases": {
        "2.31.0": [{"upload_time": "2023-05-22T14:00:00"}]
    },
}

PYPI_NOT_FOUND = {"message": "Not Found"}

NPM_EXISTS_RESPONSE = {
    "name": "lodash",
    "description": "Lodash modular utilities.",
    "dist-tags": {"latest": "4.17.21"},
    "versions": {"4.17.21": {"homepage": "https://lodash.com"}},
    "time": {
        "created": "2012-04-05T00:00:00.000Z",
        "modified": "2023-01-01T00:00:00.000Z",
    },
    "maintainers": [{"name": "jdalton"}, {"name": "mathias"}],
}

PYPI_STATS_RESPONSE = {
    "data": {"last_month": 5_000_000}
}

NPM_DOWNLOADS_RESPONSE = {
    "downloads": 50_000_000,
    "package": "lodash"
}


class TestValidateSinglePackage:
    @pytest.mark.asyncio
    @respx.mock
    async def test_existing_package_is_low_risk(self, cache):
        # Mock PyPI
        respx.get("https://pypi.org/pypi/requests/json").mock(
            return_value=httpx.Response(200, json=PYPI_EXISTS_RESPONSE)
        )
        # Mock PyPI stats
        respx.get("https://pypistats.org/api/packages/requests/recent").mock(
            return_value=httpx.Response(200, json=PYPI_STATS_RESPONSE)
        )

        async with Validator(cache=cache) as v:
            result = await v.validate("requests", Ecosystem.PYPI)

        assert result.exists_on_registry is True
        assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
        assert result.risk_score < 0.6

    @pytest.mark.asyncio
    @respx.mock
    async def test_nonexistent_package_is_high_risk(self, cache):
        pkg_name = "totally-fake-ai-package-xyz123"
        respx.get(f"https://pypi.org/pypi/{pkg_name}/json").mock(
            return_value=httpx.Response(404)
        )
        # Stats would also 404
        respx.get(
            f"https://pypistats.org/api/packages/{pkg_name}/recent"
        ).mock(return_value=httpx.Response(404))

        async with Validator(cache=cache) as v:
            result = await v.validate(pkg_name, Ecosystem.PYPI)

        assert result.exists_on_registry is False
        assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert result.risk_score >= 0.4

    @pytest.mark.asyncio
    @respx.mock
    async def test_npm_existing_package(self, cache):
        respx.get("https://registry.npmjs.org/lodash").mock(
            return_value=httpx.Response(200, json=NPM_EXISTS_RESPONSE)
        )
        respx.get("https://api.npmjs.org/downloads/point/last-month/lodash").mock(
            return_value=httpx.Response(200, json=NPM_DOWNLOADS_RESPONSE)
        )

        async with Validator(cache=cache) as v:
            result = await v.validate("lodash", Ecosystem.NPM)

        assert result.exists_on_registry is True
        assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)

    @pytest.mark.asyncio
    @respx.mock
    async def test_typosquat_detected(self, cache):
        """'reqests' (missing 'u') should be flagged as typosquat."""
        respx.get("https://pypi.org/pypi/reqests/json").mock(
            return_value=httpx.Response(404)
        )
        respx.get(
            "https://pypistats.org/api/packages/reqests/recent"
        ).mock(return_value=httpx.Response(404))

        async with Validator(cache=cache) as v:
            result = await v.validate("reqests", Ecosystem.PYPI)

        assert result.risk_score > 0.4
        assert result.heuristic_result is not None
        assert len(result.heuristic_result.similar_packages) > 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_policy_allow_overrides_everything(self, cache):
        from unittest.mock import AsyncMock, MagicMock
        from core.policy import PolicyClient

        mock_policy = MagicMock(spec=PolicyClient)
        mock_policy.check = AsyncMock(return_value="allow")

        async with Validator(cache=cache, policy_client=mock_policy) as v:
            result = await v.validate("blocked-package", Ecosystem.PYPI)

        assert result.policy_override == "allow"
        assert result.risk_level == RiskLevel.LOW
        assert not result.should_block

    @pytest.mark.asyncio
    @respx.mock
    async def test_policy_block_overrides_everything(self, cache):
        from unittest.mock import AsyncMock, MagicMock
        from core.policy import PolicyClient

        mock_policy = MagicMock(spec=PolicyClient)
        mock_policy.check = AsyncMock(return_value="block")

        async with Validator(cache=cache, policy_client=mock_policy) as v:
            result = await v.validate("trusted-package", Ecosystem.PYPI)

        assert result.policy_override == "block"
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.should_block

    @pytest.mark.asyncio
    @respx.mock
    async def test_registry_timeout_treated_as_uncertain(self, cache):
        """If registry is unreachable, don't fail hard — treat as medium risk."""
        respx.get("https://pypi.org/pypi/some-package/json").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        respx.get(
            "https://pypistats.org/api/packages/some-package/recent"
        ).mock(return_value=httpx.Response(404))

        async with Validator(cache=cache) as v:
            result = await v.validate("some-package", Ecosystem.PYPI)

        # Should not crash, and should flag registry check failure
        assert any("registry-check-failed" in f for f in result.flags)


class TestValidateMany:
    @pytest.mark.asyncio
    @respx.mock
    async def test_multiple_packages_validated(self, cache):
        packages = ["requests", "flask", "django"]
        for pkg in packages:
            respx.get(f"https://pypi.org/pypi/{pkg}/json").mock(
                return_value=httpx.Response(200, json={
                    **PYPI_EXISTS_RESPONSE,
                    "info": {**PYPI_EXISTS_RESPONSE["info"], "name": pkg}
                })
            )
            respx.get(
                f"https://pypistats.org/api/packages/{pkg}/recent"
            ).mock(return_value=httpx.Response(200, json=PYPI_STATS_RESPONSE))

        async with Validator(cache=cache) as v:
            results = await v.validate_many(
                [(pkg, Ecosystem.PYPI) for pkg in packages]
            )

        assert len(results) == 3
        for result in results:
            assert result.exists_on_registry is True


class TestScanManifest:
    @pytest.mark.asyncio
    @respx.mock
    async def test_scan_requirements_txt(self, cache, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.31.0\nnumpy>=1.24.0\n")

        # Mock both packages as existing
        for pkg in ["requests", "numpy"]:
            respx.get(f"https://pypi.org/pypi/{pkg}/json").mock(
                return_value=httpx.Response(200, json={
                    **PYPI_EXISTS_RESPONSE,
                    "info": {**PYPI_EXISTS_RESPONSE["info"], "name": pkg}
                })
            )
            respx.get(
                f"https://pypistats.org/api/packages/{pkg}/recent"
            ).mock(return_value=httpx.Response(200, json=PYPI_STATS_RESPONSE))

        async with Validator(cache=cache) as v:
            report = await v.scan_manifest(str(req), Ecosystem.PYPI)

        assert report.total_packages == 2
        assert report.ecosystem == "pypi"
        assert len(report.results) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_scan_with_hallucinated_package(self, cache, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.31.0\nnumpy-ai-helper-toolkit>=1.0\n")

        respx.get("https://pypi.org/pypi/requests/json").mock(
            return_value=httpx.Response(200, json=PYPI_EXISTS_RESPONSE)
        )
        respx.get("https://pypistats.org/api/packages/requests/recent").mock(
            return_value=httpx.Response(200, json=PYPI_STATS_RESPONSE)
        )
        respx.get("https://pypi.org/pypi/numpy-ai-helper-toolkit/json").mock(
            return_value=httpx.Response(404)
        )
        respx.get("https://pypistats.org/api/packages/numpy-ai-helper-toolkit/recent").mock(
            return_value=httpx.Response(404)
        )

        async with Validator(cache=cache) as v:
            report = await v.scan_manifest(str(req), Ecosystem.PYPI)

        assert report.total_packages == 2
        # The hallucinated package should have high risk
        hallucinated = next(r for r in report.results if "numpy-ai" in r.package_name)
        assert not hallucinated.exists_on_registry
        assert hallucinated.risk_score > 0.4


class TestRemediationMessages:
    @pytest.mark.asyncio
    @respx.mock
    async def test_nonexistent_package_has_remediation(self, cache):
        pkg = "super-fake-package-12345"
        respx.get(f"https://pypi.org/pypi/{pkg}/json").mock(
            return_value=httpx.Response(404)
        )
        respx.get(
            f"https://pypistats.org/api/packages/{pkg}/recent"
        ).mock(return_value=httpx.Response(404))

        async with Validator(cache=cache) as v:
            result = await v.validate(pkg, Ecosystem.PYPI)

        assert result.remediation is not None
        assert "not exist" in result.remediation.lower() or "hallucinated" in result.remediation.lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_typosquat_has_did_you_mean(self, cache):
        # "reqests" should suggest "requests"
        respx.get("https://pypi.org/pypi/reqests/json").mock(
            return_value=httpx.Response(404)
        )
        respx.get(
            "https://pypistats.org/api/packages/reqests/recent"
        ).mock(return_value=httpx.Response(404))

        async with Validator(cache=cache) as v:
            result = await v.validate("reqests", Ecosystem.PYPI)

        # Should have similar packages in heuristic result
        assert result.heuristic_result is not None
        assert len(result.heuristic_result.similar_packages) > 0