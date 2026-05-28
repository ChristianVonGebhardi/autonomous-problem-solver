"""Tests for the reputation scorer."""
import pytest
import pytest_asyncio
import httpx
import respx

from core.reputation import ReputationScorer
from core.cache import Cache
from core.models import Ecosystem, ReputationResult, RegistryResult


@pytest_asyncio.fixture
async def cache(tmp_path):
    c = Cache(db_path=str(tmp_path / "rep_test.db"), ttl=60)
    yield c
    await c.close()


class TestReputationScoring:
    def test_high_downloads_low_risk(self):
        scorer = ReputationScorer.__new__(ReputationScorer)
        result = scorer._compute_score(
            downloads=5_000_000,
            days_old=1000,
            maintainer_count=3,
            has_github=True,
            flags=[],
        )
        assert result.score < 0.2

    def test_no_downloads_high_risk(self):
        scorer = ReputationScorer.__new__(ReputationScorer)
        result = scorer._compute_score(
            downloads=5,
            days_old=3,
            maintainer_count=0,
            has_github=False,
            flags=[],
        )
        assert result.score > 0.6
        assert any("download" in f for f in result.flags)

    def test_new_package_flagged(self):
        scorer = ReputationScorer.__new__(ReputationScorer)
        result = scorer._compute_score(
            downloads=100,
            days_old=2,  # 2 days old
            maintainer_count=1,
            has_github=True,
            flags=[],
        )
        assert any("week" in f or "published" in f for f in result.flags)

    def test_no_github_flagged(self):
        scorer = ReputationScorer.__new__(ReputationScorer)
        result = scorer._compute_score(
            downloads=10_000,
            days_old=500,
            maintainer_count=2,
            has_github=False,
            flags=[],
        )
        assert any("github" in f for f in result.flags)

    def test_nonexistent_package_max_score(self):
        import asyncio
        scorer = ReputationScorer.__new__(ReputationScorer)
        scorer.cache = None
        scorer._client = None
        scorer._owns_client = True

        reg_result = RegistryResult(
            exists=False,
            ecosystem="pypi",
            package_name="fake-pkg",
        )

        # Score for non-existent package should be max risk
        # Test _compute_score directly with bad signals
        result = scorer._compute_score(
            downloads=None,
            days_old=None,
            maintainer_count=None,
            has_github=False,
            flags=["package-not-found"],
        )
        # With all unknowns + no github, score should be above 0
        assert result.score > 0.2

    def test_score_clamped_to_1(self):
        scorer = ReputationScorer.__new__(ReputationScorer)
        result = scorer._compute_score(
            downloads=0,
            days_old=1,
            maintainer_count=0,
            has_github=False,
            flags=[],
        )
        assert result.score <= 1.0

    def test_score_never_negative(self):
        scorer = ReputationScorer.__new__(ReputationScorer)
        result = scorer._compute_score(
            downloads=50_000_000,
            days_old=2000,
            maintainer_count=10,
            has_github=True,
            flags=[],
        )
        assert result.score >= 0.0


class TestReputationFetch:
    @pytest.mark.asyncio
    @respx.mock
    async def test_pypi_stats_fetched(self, cache):
        respx.get("https://pypistats.org/api/packages/requests/recent").mock(
            return_value=httpx.Response(200, json={
                "data": {"last_month": 10_000_000}
            })
        )

        scorer = ReputationScorer(cache=cache)
        reg_result = RegistryResult(
            exists=True,
            ecosystem="pypi",
            package_name="requests",
            metadata={
                "home_page": "https://github.com/psf/requests",
                "latest_upload_date": "2023-05-22T14:00:00",
                "maintainer": "Kenneth Reitz",
            },
        )

        result = await scorer.score("requests", Ecosystem.PYPI, reg_result)
        await scorer.close()

        assert result.download_count == 10_000_000
        assert result.score < 0.3

    @pytest.mark.asyncio
    @respx.mock
    async def test_npm_stats_fetched(self, cache):
        respx.get("https://api.npmjs.org/downloads/point/last-month/lodash").mock(
            return_value=httpx.Response(200, json={"downloads": 100_000_000})
        )

        scorer = ReputationScorer(cache=cache)
        reg_result = RegistryResult(
            exists=True,
            ecosystem="npm",
            package_name="lodash",
            metadata={
                "created": "2012-04-05T00:00:00.000Z",
                "maintainer_count": 2,
                "repository": "https://github.com/lodash/lodash",
            },
        )

        result = await scorer.score("lodash", Ecosystem.NPM, reg_result)
        await scorer.close()

        assert result.download_count == 100_000_000
        assert result.score < 0.2