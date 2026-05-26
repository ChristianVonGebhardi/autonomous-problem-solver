import asyncio
import structlog
from celery import current_task
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.config import settings

logger = structlog.get_logger()


def run_async(coro):
    """Run async function in Celery task context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="app.workers.tasks.ingest_git_repo")
def ingest_git_repo(self, repo_path: str, repo_name: str, job_id: str):
    """Celery task to ingest a local git repository."""
    logger.info("Starting git ingestion task", repo=repo_name, job_id=job_id)

    async def _run():
        from app.db.postgres import AsyncSessionLocal
        from app.db.postgres import IngestionJob, Repository
        from app.services.git_ingestion import git_ingestion_service
        from sqlalchemy import update

        async def update_progress(pct: int, message: str):
            self.update_state(
                state="PROGRESS",
                meta={"progress": pct, "message": message},
            )
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(progress=pct, metadata_={"message": message})
                )
                await session.commit()

        try:
            result = await git_ingestion_service.ingest_repository(
                repo_path=repo_path,
                repo_name=repo_name,
                progress_callback=update_progress,
            )

            # Update job and repo status
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(
                        status="completed",
                        progress=100,
                        completed_at=datetime.now(timezone.utc),
                        metadata_=result,
                    )
                )
                await session.execute(
                    update(Repository)
                    .where(Repository.name == repo_name)
                    .values(
                        status="ready",
                        last_ingested_at=datetime.now(timezone.utc),
                        file_count=result.get("stats", {}).get("files_processed", 0),
                        commit_count=result.get("stats", {}).get("commits_processed", 0),
                    )
                )
                await session.commit()

            logger.info("Git ingestion task complete", repo=repo_name)
            return {"success": True, "stats": result.get("stats", {})}

        except Exception as e:
            logger.error("Git ingestion task failed", error=str(e), repo=repo_name)
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(status="failed", error_message=str(e))
                )
                await session.execute(
                    update(Repository)
                    .where(Repository.name == repo_name)
                    .values(status="error")
                )
                await session.commit()
            raise

    return run_async(_run())


@celery_app.task(bind=True, name="app.workers.tasks.ingest_github_repo")
def ingest_github_repo(self, repo_url: str, repo_name: str, job_id: str, local_path: str):
    """Celery task to clone and ingest a GitHub repository."""
    logger.info("Starting GitHub ingestion task", repo=repo_name, job_id=job_id)

    async def _run():
        from app.db.postgres import AsyncSessionLocal
        from app.db.postgres import IngestionJob, Repository
        from app.services.github_ingestion import github_ingestion_service
        from app.services.git_ingestion import git_ingestion_service
        from sqlalchemy import update
        import re

        async def update_progress(pct: int, message: str):
            self.update_state(
                state="PROGRESS",
                meta={"progress": pct, "message": message},
            )

        try:
            # Step 1: Clone the repo
            await update_progress(5, "Cloning repository...")
            cloned = await github_ingestion_service.clone_repo(repo_url, local_path)
            if not cloned:
                raise ValueError(f"Failed to clone {repo_url}")

            # Step 2: Ingest git history
            await update_progress(10, "Ingesting git history...")
            result = await git_ingestion_service.ingest_repository(
                repo_path=local_path,
                repo_name=repo_name,
                progress_callback=update_progress,
            )

            # Step 3: Ingest PRs if GitHub token available
            if settings.github_token:
                await update_progress(90, "Fetching pull requests...")
                # Extract owner/repo from URL
                match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", repo_url)
                if match:
                    repo_full_name = match.group(1)
                    pr_result = await github_ingestion_service.ingest_pull_requests(
                        repo_name, repo_full_name
                    )
                    result["prs_ingested"] = pr_result.get("prs_ingested", 0)

            # Update DB
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(
                        status="completed",
                        progress=100,
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                await session.execute(
                    update(Repository)
                    .where(Repository.name == repo_name)
                    .values(
                        status="ready",
                        last_ingested_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

            return {"success": True}

        except Exception as e:
            logger.error("GitHub ingestion failed", error=str(e))
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(status="failed", error_message=str(e))
                )
                await session.commit()
            raise

    return run_async(_run())