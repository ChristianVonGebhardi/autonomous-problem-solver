import os
import uuid
import tempfile
import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db.postgres import get_db, Repository, IngestionJob
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()


class GitIngestRequest(BaseModel):
    repo_path: str = Field(..., description="Absolute path to local git repository")
    repo_name: str = Field(..., description="Name identifier for the repository")


class GitHubIngestRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub HTTPS URL")
    repo_name: str = Field(..., description="Name identifier for the repository")


class IngestResponse(BaseModel):
    job_id: str
    repo_name: str
    status: str
    message: str


async def _get_or_create_repo(
    db: AsyncSession,
    name: str,
    repo_path: Optional[str] = None,
    repo_url: Optional[str] = None,
) -> Repository:
    """Get existing repo or create a new one."""
    result = await db.execute(select(Repository).where(Repository.name == name))
    repo = result.scalar_one_or_none()
    if repo:
        repo.status = "ingesting"
        if repo_path:
            repo.repo_path = repo_path
        if repo_url:
            repo.repo_url = repo_url
    else:
        repo = Repository(
            id=str(uuid.uuid4()),
            name=name,
            repo_path=repo_path,
            repo_url=repo_url,
            status="ingesting",
        )
        db.add(repo)
    await db.flush()
    return repo


async def _dispatch_git_task(
    db: AsyncSession,
    job_id: str,
    repo_path: str,
    repo_name: str,
) -> Optional[str]:
    """Try to dispatch to Celery; returns celery task id or None."""
    try:
        from app.workers.tasks import ingest_git_repo
        task = ingest_git_repo.delay(repo_path, repo_name, job_id)
        return task.id
    except Exception as e:
        logger.warning("Celery not available for git task", error=str(e))
        return None


async def _dispatch_github_task(
    db: AsyncSession,
    job_id: str,
    repo_url: str,
    repo_name: str,
    clone_dir: str,
) -> Optional[str]:
    """Try to dispatch to Celery; returns celery task id or None."""
    try:
        from app.workers.tasks import ingest_github_repo
        task = ingest_github_repo.delay(repo_url, repo_name, job_id, clone_dir)
        return task.id
    except Exception as e:
        logger.warning("Celery not available for github task", error=str(e))
        return None


@router.post("/git", response_model=IngestResponse)
async def ingest_git_repository(
    request: GitIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a local git repository."""
    # Validate path exists
    if not os.path.exists(request.repo_path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {request.repo_path}",
        )

    git_dir = os.path.join(request.repo_path, ".git")
    if not os.path.exists(git_dir):
        raise HTTPException(
            status_code=400,
            detail=f"Not a git repository (no .git directory found at {request.repo_path})",
        )

    # Create/update repository record
    repo = await _get_or_create_repo(db, request.repo_name, repo_path=request.repo_path)

    # Create ingestion job
    job = IngestionJob(
        id=str(uuid.uuid4()),
        repo_name=request.repo_name,
        job_type="git",
        status="pending",
    )
    db.add(job)
    await db.flush()
    await db.commit()

    # Try Celery first; fall back to inline async execution
    celery_task_id = await _dispatch_git_task(db, job.id, request.repo_path, request.repo_name)

    if celery_task_id:
        async with db.begin_nested() if False else db:
            pass
        # Update job with celery task id (re-open session)
        from app.db.postgres import AsyncSessionLocal
        async with AsyncSessionLocal() as session2:
            await session2.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job.id)
                .values(celery_task_id=celery_task_id, status="running")
            )
            await session2.commit()
        status_msg = "running"
    else:
        # Inline ingestion (no Celery)
        logger.info("Running ingestion inline (no Celery)", repo=request.repo_name)
        try:
            from app.services.git_ingestion import git_ingestion_service
            from app.db.postgres import AsyncSessionLocal

            result = await git_ingestion_service.ingest_repository(
                request.repo_path, request.repo_name
            )
            async with AsyncSessionLocal() as session2:
                await session2.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job.id)
                    .values(status="completed", progress=100)
                )
                await session2.execute(
                    update(Repository)
                    .where(Repository.name == request.repo_name)
                    .values(
                        status="ready",
                        last_ingested_at=datetime.now(timezone.utc),
                        file_count=result.get("stats", {}).get("files_processed", 0),
                        commit_count=result.get("stats", {}).get("commits_processed", 0),
                    )
                )
                await session2.commit()
        except Exception as e:
            logger.error("Inline git ingestion failed", error=str(e))
            from app.db.postgres import AsyncSessionLocal
            async with AsyncSessionLocal() as session2:
                await session2.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job.id)
                    .values(status="failed", error_message=str(e))
                )
                await session2.execute(
                    update(Repository)
                    .where(Repository.name == request.repo_name)
                    .values(status="error")
                )
                await session2.commit()
        status_msg = "completed"

    return IngestResponse(
        job_id=job.id,
        repo_name=request.repo_name,
        status=status_msg,
        message=f"Ingestion started for '{request.repo_name}'",
    )


@router.post("/github", response_model=IngestResponse)
async def ingest_github_repository(
    request: GitHubIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Clone and ingest a GitHub repository."""
    clone_dir = os.path.join("/tmp/repos", request.repo_name)
    os.makedirs(clone_dir, exist_ok=True)

    # Create/update DB records
    repo = await _get_or_create_repo(
        db, request.repo_name, repo_url=request.repo_url, repo_path=clone_dir
    )

    job = IngestionJob(
        id=str(uuid.uuid4()),
        repo_name=request.repo_name,
        job_type="github",
        status="pending",
    )
    db.add(job)
    await db.flush()
    await db.commit()

    # Try Celery first
    celery_task_id = await _dispatch_github_task(
        db, job.id, request.repo_url, request.repo_name, clone_dir
    )

    if celery_task_id:
        from app.db.postgres import AsyncSessionLocal
        async with AsyncSessionLocal() as session2:
            await session2.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job.id)
                .values(celery_task_id=celery_task_id, status="running")
            )
            await session2.commit()
        status_msg = "running"
    else:
        # Inline fallback
        logger.info("Running GitHub ingestion inline (no Celery)", repo=request.repo_name)
        try:
            from app.services.github_ingestion import github_ingestion_service
            from app.services.git_ingestion import git_ingestion_service
            from app.db.postgres import AsyncSessionLocal

            cloned = await github_ingestion_service.clone_repo(request.repo_url, clone_dir)
            if not cloned:
                raise ValueError(f"Failed to clone repository: {request.repo_url}")

            result = await git_ingestion_service.ingest_repository(clone_dir, request.repo_name)

            # Optionally ingest PRs
            if settings.github_token:
                import re
                match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", request.repo_url)
                if match:
                    await github_ingestion_service.ingest_pull_requests(
                        request.repo_name, match.group(1)
                    )

            async with AsyncSessionLocal() as session2:
                await session2.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job.id)
                    .values(status="completed", progress=100)
                )
                await session2.execute(
                    update(Repository)
                    .where(Repository.name == request.repo_name)
                    .values(
                        status="ready",
                        last_ingested_at=datetime.now(timezone.utc),
                        file_count=result.get("stats", {}).get("files_processed", 0),
                        commit_count=result.get("stats", {}).get("commits_processed", 0),
                    )
                )
                await session2.commit()
        except Exception as e:
            logger.error("Inline GitHub ingestion failed", error=str(e))
            from app.db.postgres import AsyncSessionLocal
            async with AsyncSessionLocal() as session2:
                await session2.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job.id)
                    .values(status="failed", error_message=str(e))
                )
                await session2.execute(
                    update(Repository)
                    .where(Repository.name == request.repo_name)
                    .values(status="error")
                )
                await session2.commit()
        status_msg = "completed"

    return IngestResponse(
        job_id=job.id,
        repo_name=request.repo_name,
        status=status_msg,
        message=f"GitHub ingestion started for '{request.repo_name}'",
    )


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get ingestion job status and Celery progress."""
    result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check Celery task state for live progress
    celery_state = None
    if job.celery_task_id:
        try:
            from app.workers.celery_app import celery_app
            task = celery_app.AsyncResult(job.celery_task_id)
            info = task.info if isinstance(task.info, dict) else {}
            celery_state = {
                "state": task.state,
                "info": info,
            }
            # Sync progress from Celery PROGRESS state
            if task.state == "PROGRESS" and info.get("progress") is not None:
                job.progress = info["progress"]
        except Exception as e:
            logger.debug("Could not get Celery task state", error=str(e))

    return {
        "job_id": job.id,
        "repo_name": job.repo_name,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "error_message": job.error_message,
        "celery_state": celery_state,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/repositories")
async def list_repositories(db: AsyncSession = Depends(get_db)):
    """List all ingested repositories."""
    result = await db.execute(select(Repository))
    repos = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "repo_path": r.repo_path,
            "repo_url": r.repo_url,
            "status": r.status,
            "file_count": r.file_count or 0,
            "commit_count": r.commit_count or 0,
            "last_ingested_at": r.last_ingested_at.isoformat() if r.last_ingested_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in repos
    ]