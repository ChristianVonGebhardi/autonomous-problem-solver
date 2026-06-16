"""Business value ingestion — GitHub, Jira, webhook connectors."""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import ValueEvent
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def ingest_github_prs(
    db: AsyncSession,
    repo: Optional[str] = None,
    since_days: int = 7,
) -> int:
    """Fetch merged PRs from GitHub and create value events."""
    if not settings.GITHUB_TOKEN:
        logger.info("GitHub token not configured, skipping PR ingestion")
        return 0

    headers = {
        "Authorization": f"token {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    count = 0
    since = datetime.utcnow()
    from datetime import timedelta
    since_dt = (since - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    repos = [repo] if repo else []
    if settings.GITHUB_ORG and not repos:
        # List repos for org
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://api.github.com/orgs/{settings.GITHUB_ORG}/repos",
                    headers=headers,
                    params={"per_page": 10, "sort": "updated"},
                )
                resp.raise_for_status()
                repos = [r["full_name"] for r in resp.json()[:5]]
        except Exception as e:
            logger.error(f"Failed to list GitHub repos: {e}")
            return 0

    for full_repo in repos:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{full_repo}/pulls",
                    headers=headers,
                    params={"state": "closed", "sort": "updated", "since": since_dt, "per_page": 20},
                )
                resp.raise_for_status()
                prs = resp.json()

            for pr in prs:
                if pr.get("merged_at"):
                    event = ValueEvent(
                        source="github",
                        event_type="pr_merged",
                        business_entity_id=str(pr["number"]),
                        value_points=1.0,
                        title=pr.get("title"),
                        url=pr.get("html_url"),
                        timestamp=datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00")).replace(tzinfo=None),
                        extra={"repo": full_repo, "author": pr.get("user", {}).get("login")},
                    )
                    db.add(event)
                    count += 1

        except Exception as e:
            logger.error(f"Failed to ingest PRs from {full_repo}: {e}")

    if count > 0:
        await db.commit()
    return count


async def create_value_event_from_webhook(
    db: AsyncSession,
    payload: Dict[str, Any],
) -> ValueEvent:
    """Create a value event from a generic webhook payload."""
    event = ValueEvent(
        source=payload.get("source", "webhook"),
        event_type=payload.get("event_type", "custom"),
        team=payload.get("team"),
        feature=payload.get("feature"),
        business_entity_id=payload.get("business_entity_id"),
        value_points=float(payload.get("value_points", 1.0)),
        value_usd=float(payload["value_usd"]) if payload.get("value_usd") else None,
        title=payload.get("title"),
        url=payload.get("url"),
        timestamp=datetime.utcnow(),
        extra=payload.get("extra"),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event